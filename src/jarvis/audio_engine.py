"""Background microphone, transcription, and speech synthesis pipeline."""

from __future__ import annotations

import asyncio
import array
import ctypes
import difflib
import math
import os
import queue
import re
import sysconfig
import tempfile
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any


_CUDA_DLL_DIRECTORY_HANDLES: list[Any] = []


class AudioEngine:
    """Runs the complete audio workflow outside the Tkinter thread."""

    def __init__(
        self,
        event_queue: queue.Queue[tuple[str, str]],
        command_permission: threading.Event | None = None,
        navigation_permission: threading.Event | None = None,
    ) -> None:
        self._events = event_queue
        self._command_permission = command_permission or threading.Event()
        self._navigation_permission = navigation_permission or threading.Event()
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._whisper_model: Any | None = None
        self._whisper_device: str | None = None
        self._last_detected_language: str | None = None
        self._local_tts: Any | None = None

    def start(self) -> bool:
        """Start listening in a daemon thread; return false if one is active."""
        if self._thread is not None and self._thread.is_alive():
            return False

        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            args=(self._stop_event,),
            name="jarvis-audio",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """Request that the audio loop stop after its current blocking operation."""
        if self._stop_event is not None:
            self._stop_event.set()

    def _post(self, event_type: str, message: str) -> None:
        self._events.put((event_type, message))

    @staticmethod
    def _cuda_runtime_available() -> bool:
        if os.name != "nt":
            return True
        nvidia_packages = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
        for dll_directory in nvidia_packages.glob("*/bin"):
            try:
                _CUDA_DLL_DIRECTORY_HANDLES.append(
                    os.add_dll_directory(str(dll_directory))
                )
            except OSError:
                continue
        try:
            ctypes.WinDLL("cublas64_12.dll")
            ctypes.WinDLL("cudnn64_9.dll")
        except OSError:
            return False
        return True

    def _get_whisper_model(self, device: str | None = None) -> Any:
        if self._whisper_model is None:
            from faster_whisper import WhisperModel

            if device is None:
                device = "cuda" if self._cuda_runtime_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            if device == "cpu":
                self._post(
                    "status",
                    "No se encontraron las DLL CUDA requeridas; usando Whisper en CPU (int8).",
                )
            else:
                self._post("status", "Cargando modelo local Whisper (base) en CUDA...")
            started_at = time.perf_counter()
            self._whisper_model = WhisperModel(
                "base",
                device=device,
                compute_type=compute_type,
            )
            self._whisper_device = device
            elapsed = time.perf_counter() - started_at
            self._post(
                "timing",
                f"Whisper cargado en {elapsed:.1f} s ({device}); se reutilizará mientras la app esté abierta.",
            )
        return self._whisper_model

    @staticmethod
    def _is_missing_cuda_library(error: Exception) -> bool:
        message = str(error).lower()
        mentions_cuda_library = any(name in message for name in ("cublas", "cudnn", "cuda"))
        indicates_load_failure = any(
            phrase in message
            for phrase in ("not found", "cannot be loaded", "could not load", "failed to load")
        )
        return mentions_cuda_library and indicates_load_failure

    def _transcribe_audio(
        self,
        audio_path: str,
        stop_event: threading.Event,
        language: str | None = None,
        wake_word_retry: bool = False,
    ) -> str:
        model = self._get_whisper_model()
        transcription_options = {
            "language": language,
            "vad_filter": not wake_word_retry,
            "beam_size": 3,
            "condition_on_previous_text": False,
            "no_speech_threshold": None if wake_word_retry else 0.6,
            "log_prob_threshold": -2.0 if wake_word_retry else -1.0,
            "hotwords": "Jarvis" if wake_word_retry else None,
        }
        try:
            segments, info = model.transcribe(
                audio_path,
                **transcription_options,
            )
            self._last_detected_language = getattr(info, "language", None)
            return "".join(segment.text for segment in segments).strip()
        except Exception as error:
            if self._whisper_device != "cuda" or not self._is_missing_cuda_library(error):
                raise

            self._whisper_model = None
            self._whisper_device = None
            if stop_event.is_set():
                return ""
            self._post(
                "status",
                f"CUDA no puede cargar sus DLL ({error}); cambiando a CPU para esta sesión.",
            )
            model = self._get_whisper_model(device="cpu")
            segments, info = model.transcribe(
                audio_path,
                **transcription_options,
            )
            self._last_detected_language = getattr(info, "language", None)
            return "".join(segment.text for segment in segments).strip()

    def _request_orchestrator(
        self, orchestrator: Any, transcript: str
    ) -> tuple[str, str] | None:
        self._post("status", "Enrutando solicitud...")
        request_started_at = time.perf_counter()
        try:
            response = orchestrator.respond_with_source(
                transcript,
                allow_system_commands=self._command_permission.is_set(),
                allow_navigation=self._navigation_permission.is_set(),
            )
        except Exception as error:
            if getattr(error, "code", None) == 429 or "429" in str(error):
                self._post(
                    "warning",
                    "Gemini alcanzó el límite de cuota (HTTP 429). No se generó respuesta; el asistente seguirá escuchando. Revisa tu cuota o plan de Google AI.",
                )
            else:
                self._post(
                    "warning",
                    f"El orquestador no pudo responder ({type(error).__name__}): {str(error)[:240]}. El asistente seguirá escuchando.",
                )
            return None

        request_elapsed = time.perf_counter() - request_started_at
        self._post("timing", f"El orquestador respondió en {request_elapsed:.1f} s.")
        self._post("response", response.text)
        return response.text, response.source

    def _run(self, stop_event: threading.Event) -> None:
        try:
            self._listen_loop(stop_event)
        except Exception as error:
            self._post("error", f"Error del motor de audio: {error}")
        finally:
            if self._local_tts is not None:
                try:
                    self._local_tts.stop()
                except Exception as error:
                    self._post("warning", f"No se pudo cerrar pyttsx3: {error}")
                self._local_tts = None
            self._post("stopped", "Motor de audio detenido.")

    def _listen_loop(self, stop_event: threading.Event) -> None:
        import speech_recognition as sr
        from jarvis.orchestrator import Orchestrator

        orchestrator = Orchestrator()
        self._get_whisper_model()
        if stop_event.is_set():
            return
        recognizer = sr.Recognizer()

        self._post("status", "Preparando micrófono...")
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        with sr.Microphone() as microphone:
            recognizer.adjust_for_ambient_noise(microphone, duration=1.5)
            self._post("status", "Sistema en línea. Escuchando...")
            wake_pending_until: float | None = None

            while not stop_event.is_set():
                try:
                    audio = recognizer.listen(
                        microphone,
                        timeout=1,
                        phrase_time_limit=10,
                    )
                except sr.WaitTimeoutError:
                    continue

                if stop_event.is_set():
                    break

                self._post("status", "Transcribiendo audio localmente...")
                transcription_started_at = time.perf_counter()
                audio_duration = self._audio_duration_seconds(audio)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
                    audio_path = audio_file.name

                try:
                    with open(audio_path, "wb") as audio_file:
                        audio_file.write(audio.get_wav_data())
                    transcript = self._transcribe_audio(audio_path, stop_event)
                    if (
                        (audio_duration is not None and 0 < audio_duration <= 5)
                        and self._remove_wake_word(transcript) is None
                        and wake_pending_until is None
                        and not stop_event.is_set()
                    ):
                        self._post(
                            "status",
                            "No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.",
                        )
                        for language in ("es", "en"):
                            retry_transcript = self._transcribe_audio(
                                audio_path,
                                stop_event,
                                language=language,
                                wake_word_retry=True,
                            )
                            if self._remove_wake_word(retry_transcript) is not None:
                                transcript = retry_transcript
                                break
                            if stop_event.is_set():
                                break
                finally:
                    try:
                        os.remove(audio_path)
                    except OSError:
                        pass
                transcription_elapsed = time.perf_counter() - transcription_started_at
                if stop_event.is_set():
                    self._post("status", "Apagado solicitado; se descartó la transcripción en curso.")
                    break

                if not transcript:
                    language = self._last_detected_language or "desconocido"
                    level = self._audio_level_dbfs(audio)
                    level_message = f"; nivel de entrada {level:.0f} dBFS" if level is not None else ""
                    self._post(
                        "status",
                        f"Sistema en línea. Whisper no detectó voz (idioma: {language}{level_message}); sigo escuchando.",
                    )
                    continue

                command = self._remove_wake_word(transcript)
                if command is None and wake_pending_until is not None:
                    if time.monotonic() <= wake_pending_until:
                        command = transcript
                        self._post(
                            "status",
                            "Sistema en línea. Wake word detectado; procesando la frase siguiente.",
                        )
                    wake_pending_until = None
                if command is None:
                    language = self._last_detected_language or "desconocido"
                    level = self._audio_level_dbfs(audio)
                    level_message = f"; nivel de entrada {level:.0f} dBFS" if level is not None else ""
                    self._post(
                        "status",
                        f"Sistema en línea. Frase descartada: no se detectó 'Jarvis' (idioma: {language}{level_message}); sigo escuchando.",
                    )
                    continue

                self._post("timing", f"Whisper transcribió en {transcription_elapsed:.1f} s.")
                self._post("transcription", transcript)
                if stop_event.is_set():
                    break

                if not command:
                    self._speak("Te escucho. I'm listening.", "local", stop_event)
                    wake_pending_until = time.monotonic() + 8
                    self._post(
                        "status",
                        "Sistema en línea. Wake word detectado; di tu solicitud en los próximos 8 segundos.",
                    )
                    continue

                response = self._request_orchestrator(orchestrator, command)
                if response is None:
                    if stop_event.is_set():
                        break
                    self._post("status", "Sistema en línea. Escuchando...")
                    continue
                response_text, response_source = response
                if stop_event.is_set():
                    break

                self._post("status", "Generando respuesta de voz...")
                speech_started_at = time.perf_counter()
                self._speak(response_text, response_source, stop_event)
                speech_elapsed = time.perf_counter() - speech_started_at
                self._post("timing", f"Síntesis y reproducción de voz: {speech_elapsed:.1f} s.")
                if not stop_event.is_set():
                    self._post("status", "Sistema en línea. Escuchando...")

    def _speak(self, text: str, source: str, stop_event: threading.Event) -> None:
        use_cloud_voice = os.getenv("JARVIS_CLOUD_TTS", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if source == "gemini" and use_cloud_voice:
            self._speak_cloud(text, stop_event)
        else:
            self._speak_local(text)

    @staticmethod
    def _audio_duration_seconds(audio: Any) -> float | None:
        sample_rate = getattr(audio, "sample_rate", 0)
        sample_width = getattr(audio, "sample_width", 0)
        frame_data = getattr(audio, "frame_data", b"")
        if not sample_rate or not sample_width:
            return None
        return len(frame_data) / (sample_rate * sample_width)

    @staticmethod
    def _audio_level_dbfs(audio: Any) -> float | None:
        sample_width = getattr(audio, "sample_width", 0)
        frame_data = getattr(audio, "frame_data", b"")
        if sample_width not in (1, 2, 4) or not frame_data:
            return None
        if sample_width == 1:
            samples = [sample - 128 for sample in frame_data]
            full_scale = 128
        else:
            sample_type = "h" if sample_width == 2 else "i"
            sample_array = array.array(sample_type)
            sample_array.frombytes(frame_data[: len(frame_data) - len(frame_data) % sample_width])
            samples = sample_array
            full_scale = 1 << (sample_width * 8 - 1)
        sample_count = len(samples)
        if not sample_count:
            return None
        rms = math.sqrt(sum(sample * sample for sample in samples) / sample_count)
        if rms == 0:
            return float("-inf")
        return 20 * math.log10(rms / full_scale)

    @staticmethod
    def _remove_wake_word(transcript: str) -> str | None:
        wake_matches = []
        for match in re.finditer(r"\b\w+\b", transcript, flags=re.IGNORECASE):
            normalized_word = unicodedata.normalize("NFD", match.group())
            normalized_word = "".join(
                character
                for character in normalized_word
                if not unicodedata.combining(character)
            )
            normalized = normalized_word.casefold()
            if normalized in {
                "jarvis",
                "yarbis",
                "llarbis",
                "ybis",
                "yabis",
                "llarbi",
                "yarbi",
                "yarvis",
                "llarvis",
                "yavis",
                "llavis",
            } or (
                len(normalized) >= 5
                and difflib.SequenceMatcher(None, normalized, "jarvis").ratio() >= 0.8
            ):
                wake_matches.append(match)
        if not wake_matches:
            return None

        command = transcript
        for match in reversed(wake_matches):
            command = command[:match.start()] + " " + command[match.end():]
        return re.sub(r"\s+", " ", command).strip(" \t\r\n,.:;!?¿¡-")

    def _speak_local(self, text: str) -> None:
        if self._local_tts is None:
            import pyttsx3

            self._local_tts = pyttsx3.init()
        self._local_tts.say(text)
        self._local_tts.runAndWait()

    @staticmethod
    def _speak_cloud(text: str, stop_event: threading.Event) -> None:
        import edge_tts
        import pygame

        async def synthesize(output_path: str) -> None:
            speech = edge_tts.Communicate(text, "es-MX-DaliaNeural")
            await speech.save(output_path)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as audio_file:
            audio_path = audio_file.name

        try:
            asyncio.run(synthesize(audio_path))
            pygame.mixer.init()
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not stop_event.wait(0.1):
                pass
            pygame.mixer.music.stop()
        finally:
            if pygame.mixer.get_init():
                pygame.mixer.quit()
            try:
                os.remove(audio_path)
            except OSError:
                pass
