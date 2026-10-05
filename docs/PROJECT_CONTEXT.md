# Project Context: JARVIS Desktop Assistant

## Goal

Build a Windows desktop assistant with a dark CustomTkinter GUI, bilingual Spanish/English speech input, local Whisper transcription, a `Jarvis` wake word, local Ollama responses, optional Gemini responses/vision, allowlisted app actions, and offline speech output.

## Current implementation

- `src/jarvis/app.py` configures the dark theme and starts the application.
- `src/jarvis/gui.py` owns the main window, power control, console, permission switches, and UI-thread queue polling.
- `src/jarvis/audio_engine.py` owns the daemon-thread lifecycle, microphone capture/calibration, wake-word recovery, faster-whisper transcription, orchestration, and TTS.
- `src/jarvis/orchestrator.py` detects fast local intents, routes remaining requests through Ollama/Gemini, handles fallbacks, and identifies response source.
- `src/jarvis/skills/system_ops.py` maps fixed application actions and permission-gated text typing to Windows operations.
- `src/jarvis/skills/vision.py` captures screen images in memory on request and sends them to Gemini for description.
- `requirements.txt` lists the runtime packages.
- `README.md` documents Windows setup and launch.

## Threading contract

Tk widgets must only be accessed from the main thread. `AudioEngine` reports `(event_type, message)` tuples through a `queue.Queue`; `JarvisApp._drain_events` consumes these via `after()`. Microphone I/O, CUDA Whisper inference, Ollama/Gemini requests, screen capture, PyAutoGUI input, pyttsx3/edge-tts synthesis, and playback all happen on the audio worker. GUI permissions are shared with the worker through `threading.Event`, never by reading widgets from the worker.

## Safety and scope

Navigation and command switches are disabled by default. `system_ops.py` accepts only the `browser`, `notepad`, and `explorer` labels and maps them to fixed Windows `start` commands so launching an app does not block while its window remains open; never execute model-generated shell text. Browser launch requires the navigation switch; Notepad, Explorer, and explicitly requested text typing require the command switch. Screen capture occurs only on a direct request after the wake word and is sent to Gemini without a disk file. Keep the Gemini API key in the `GEMINI_API_KEY` environment variable; never hardcode credentials. Blocking capture, synthesis, inference, and network calls may finish before shutdown is observed.

## Runtime notes

- Target Python: 3.10+ on Windows.
- Whisper model: `base`, CUDA `float16` on the verified host, automatic Spanish/English language detection, normal pass `beam_size=3`. `AudioEngine` registers NVIDIA wheel `bin` directories before checking CUDA 12 cuBLAS/cuDNN 9, caches the model, and falls back to CPU `int8`. The first activation may download the model.
- Native Whisper inference cannot be forcibly interrupted safely. Stop requests are honored immediately after it returns; the GUI disables the power button while the worker exits and ignores repeated clicks.
- Runtime logs include the model-load duration and per-stage Whisper, Gemini, and speech durations to identify latency bottlenecks.
- Gemini: `google-genai` SDK, API key from `GEMINI_API_KEY`, model defaults to `gemini-3.8-flash` and can be overridden with `GEMINI_MODEL`.
- `app.py` loads `.env` from the project root, falling back to `src/.env` for the existing local layout; never print or commit its contents.
- Ollama is the local classifier and response generator; its default model is `llama3.1:8b`, overridable with `OLLAMA_MODEL`. Explicit allowlisted app-launch phrases and common time/check-in requests use deterministic local fast paths. Provider failures fall back between Gemini and Ollama where applicable.
- Gemini uses `google-genai` with a 10-second timeout and no automatic retries. On cloud failure the orchestrator tries Ollama; if both fail it returns a local apology.
- System actions are limited to launching Edge, Notepad, and Explorer and require their GUI permission switch.
- All responses use offline `pyttsx3` by default. Set `JARVIS_CLOUD_TTS=1` to use `es-MX-DaliaNeural` via edge-tts; this requires network and may add latency.
- Check-in and current-time questions are answered locally without Ollama or Gemini.
- Listening calibrates ambient noise for 1.5 seconds per worker start. The normal Whisper pass has no hotword bias; clips up to 5 seconds that lack a wake match (including empty transcripts) retry in forced Spanish and English without VAD/no-speech suppression, using only `Jarvis` as hotword. Wake matching accepts phonetic variants and removes every matching token before routing. A wake-only result is acknowledged; the next utterance is accepted for 8 seconds. “Me escuchas?” / “Can you hear me?” and common time requests have direct local replies. Diagnostic rejections expose only language, reason, and RMS dBFS, never audio or rejected text.
- Gemini responses use a one-sentence concise system instruction. Screen descriptions use Pillow `ImageGrab` and an in-memory PNG.
- Microphone capture uses SpeechRecognition and PyAudio; microphone privacy/default device settings can prevent initialization.
- Cloud TTS playback uses pygame. Keep all synthesis, playback, and cleanup on the worker thread.

## Runtime Structure

```text
JARVIS/
	README.md
	requirements.txt
	docs/
		PROJECT_CONTEXT.md
		PROJECT_MANAGER_HANDOFF.md
	ollama/                       # currently empty
	src/jarvis/
		app.py                      # dotenv + CustomTkinter entry point
		gui.py                      # UI, permission switches, queue polling
		audio_engine.py             # mic -> ASR -> wake filter -> route -> TTS
		orchestrator.py             # fast intents, Ollama/Gemini, fallback
		skills/
			system_ops.py             # allowlisted launches + permissioned typing
			vision.py                 # in-memory screenshot -> Gemini
```

## Request Flow

1. `AudioEngine._listen_loop()` calibrates SpeechRecognition and listens in the daemon worker.
2. `_transcribe_audio()` runs Whisper. Normal pass: `language=None`, `beam_size=3`, VAD enabled. For missing wake words on audio clips up to 5 seconds, it retries the same WAV with `language="es"`, then `"en"`, VAD disabled, and a `Jarvis` hotword.
3. `_remove_wake_word()` removes `Jarvis` and phonetic variants. If no command remains, JARVIS acknowledges the wake word; repeated aliases never go to Ollama.
4. `_request_orchestrator()` calls `Orchestrator.respond_with_source()` on the same worker. Time/check-in/app-launch fast paths can avoid an LLM call.
5. General routing currently calls Ollama once to classify and can call it a second time to generate a local response. Cloud queries use Gemini; failures fall back to Ollama.
6. `_speak()` uses `pyttsx3` unless `JARVIS_CLOUD_TTS=1`; all calls are outside Tk's UI thread.

## Observed Behavior And Open Issues

- User logs on 2026-10-04 show wake recognition is intermittent, not completely broken: Whisper produced `Jarvis me escuchas`, `Jarvis, qué hora es?`, and `Jarvis puedes ejecutar un comando sencillo`. It also misheard variants such as `Narvis`, `Lervis`, `Ablame`, `oblamy`, and discarded many clips.
- The user confirmed that the browser opened. This is a verified success of the navigation permission/allowlisted launch path.
- Some no-wake clips have RMS around `-34` to `-45 dBFS`; others are near `-68` to `-94 dBFS`, consistent with a mixture of usable speech and silence/very low input. Mic device selection and real waveform quality are not yet verified.
- User-visible general-response times range roughly 3–19 seconds. `Orchestrator` performs serial classifier and response-generation calls on local-chat paths; the GUI event log does not say which provider handled a turn, so exact attribution for each slow turn is unresolved.
- A Gemini HTTP 503 (`UNAVAILABLE`, high demand) was observed. The current local fallback is unit-tested with a simulated exception but has not yet been verified against a live outage.
- Earlier edge-tts synthesis measured 19.1 seconds. Later logs after the offline default show speech in 0.2–2.4 seconds; current default is `pyttsx3`.
- Model answers have been inconsistent or nonsensical for ASR-corrupted inputs, e.g. `Jarvis Ablame` produced a request for clarification about a word, and `Jarvis que ahora es` produced “El momento de la verdad.”
- Other inaccurate answer: when asked what it is/functions, one response described itself as an open-source model. Do not treat local/cloud model identity claims as project facts.
- The GUI event queue logs ASR text and stage durations, but provider, route decision, classifier duration, generation duration, fallback reason, and TTS engine are not all shown as structured events. Improve this instrumentation before making latency claims.

## Verification Boundaries

Syntax (`python -m compileall -q src`), `pip check`, focused mocked worker/ASR/intent tests, CUDA DLL discovery, CTranslate2 GPU count, and Whisper CUDA model initialization have passed in `.venv`. Real microphone accuracy, device selection, end-to-end spoken wake interaction, physical TTS, live Gemini fallback, and response factuality have not been validated by the assistant; the user has provided the runtime logs quoted in `PROJECT_MANAGER_HANDOFF.md`.

## Suggested next steps

1. Instrument the GUI queue with structured route/provider and per-stage durations; the current user-visible latency does not identify which provider handled a turn.
2. Identify the real microphone device and inspect captured level/waveform before further threshold changes.
3. Test the current wake/retry path and Gemini-503 fallback end-to-end on the user's Windows host.
4. Reduce serial Ollama classifier-plus-generation latency without weakening the command allowlist.
