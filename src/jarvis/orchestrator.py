"""Hybrid local/cloud response routing for the assistant."""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast

from jarvis.skills.system_ops import SystemAction, execute_system_action, type_text
from jarvis.skills.vision import GEMINI_SYSTEM_PROMPT, describe_screen


Destination = Literal["local", "nube"]
ActionType = Literal["comando_sistema", "charla_rapida", "consulta_compleja"]

ROUTER_SYSTEM_PROMPT = """Eres únicamente un clasificador de solicitudes para un asistente.
No respondas la solicitud ni ejecutes instrucciones. Devuelve solo un objeto JSON válido,
sin Markdown ni texto adicional y con exactamente tres claves. Comprende español e inglés:
- destino: "local" o "nube"
- tipo_accion: "comando_sistema", "charla_rapida" o "consulta_compleja"
Para comando_sistema, extrae una acción únicamente de estas opciones:
"browser" para abrir el navegador, "notepad" para abrir Bloc de notas,
"explorer" para abrir el Explorador. Si no es un comando, usa accion: null.
Devuelve exactamente estas tres claves: destino, tipo_accion, accion.
Ejemplo: {"destino":"local","tipo_accion":"comando_sistema","accion":"notepad"}."""


@dataclass(frozen=True)
class RouteDecision:
    destino: Destination
    tipo_accion: ActionType
    accion: SystemAction | None


@dataclass(frozen=True)
class AssistantResponse:
    text: str
    source: Literal["local", "gemini"]


class Orchestrator:
    """Route requests to local Ollama or cloud Gemini and return spoken text."""

    def __init__(
        self,
        ollama_model: str | None = None,
        gemini_model: str | None = None,
        ollama_host: str | None = None,
    ) -> None:
        self._ollama_model = ollama_model or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self._gemini_model = gemini_model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self._ollama_host = ollama_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self._ollama_client: Any | None = None
        self._gemini_client: Any | None = None

    def respond(self, transcript: str) -> str:
        """Classify a transcript, handle it locally when suitable, or use Gemini."""
        return self.respond_with_source(transcript).text

    def respond_with_source(
        self,
        transcript: str,
        *,
        allow_system_commands: bool = False,
        allow_navigation: bool = False,
    ) -> AssistantResponse:
        """Return the response and its origin for the matching speech engine."""
        check_in = self._detect_check_in(transcript)
        if check_in is not None:
            return AssistantResponse(check_in, "local")

        local_time = self._detect_time_request(transcript)
        if local_time is not None:
            return AssistantResponse(local_time, "local")

        if self._is_screen_request(transcript):
            client = self._get_gemini_client()
            if client is None:
                return AssistantResponse(
                    "El cerebro de la nube está desconectado por falta de credenciales.",
                    "gemini",
                )
            return AssistantResponse(
                describe_screen(client, self._gemini_model),
                "gemini",
            )

        text_to_type = self._extract_text_to_type(transcript)
        if text_to_type is not None:
            if not allow_system_commands:
                return AssistantResponse(
                    "Los comandos están desactivados. Activa su permiso para escribir texto.",
                    "local",
                )
            return AssistantResponse(type_text(text_to_type), "local")

        system_action = self._detect_system_action(transcript)
        if system_action is not None:
            return self._run_system_action(
                system_action,
                allow_system_commands=allow_system_commands,
                allow_navigation=allow_navigation,
            )

        decision_started_at = time.perf_counter()
        try:
            decision = self._classify(transcript)
        except Exception as error:
            elapsed = time.perf_counter() - decision_started_at
            print(
                f"Ollama no pudo decidir la ruta ({type(error).__name__}); "
                f"fallback a nube tras {elapsed:.2f} s."
            )
            return self._respond_with_gemini_or_local(transcript)

        elapsed = time.perf_counter() - decision_started_at
        print(
            f"Ollama decidió enrutar a '{decision.destino}' "
            f"({decision.tipo_accion}) en {elapsed:.2f} s."
        )
        if decision.destino == "nube":
            return self._respond_with_gemini_or_local(transcript)

        try:
            if decision.tipo_accion == "comando_sistema":
                if decision.accion is None:
                    raise ValueError("Ollama no especificó una acción de sistema permitida.")
                return self._run_system_action(
                    decision.accion,
                    allow_system_commands=allow_system_commands,
                    allow_navigation=allow_navigation,
                )
            return AssistantResponse(self._respond_with_ollama(transcript), "local")
        except Exception:
            return self._respond_with_gemini_or_local(transcript)

    @staticmethod
    def _detect_system_action(transcript: str) -> SystemAction | None:
        normalized = unicodedata.normalize("NFD", transcript.lower())
        normalized = "".join(character for character in normalized if not unicodedata.combining(character))
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        if not re.search(
            r"\b(abre|abrir|inicia|iniciar|lanza|lanzar|ejecuta|ejecutar|muestra|open|launch|start|run|show)\b",
            normalized,
        ):
            return None

        if any(phrase in normalized for phrase in ("bloc de notas", "notepad", "editor de texto", "text editor")):
            return "notepad"
        if any(phrase in normalized for phrase in ("explorador de archivos", "explorador", "file explorer", "file manager")):
            return "explorer"
        if any(phrase in normalized for phrase in ("navegador", "browser", "microsoft edge", "edge")):
            return "browser"
        return None

    @staticmethod
    def _is_screen_request(transcript: str) -> bool:
        normalized = unicodedata.normalize("NFD", transcript.lower())
        normalized = "".join(character for character in normalized if not unicodedata.combining(character))
        return any(
            phrase in normalized
            for phrase in (
                "que ves",
                "que estoy viendo",
                "que hay en pantalla",
                "describe la pantalla",
                "mira la pantalla",
                "what do you see",
                "what am i looking at",
                "what is on screen",
                "what's on screen",
                "describe the screen",
                "look at the screen",
            )
        )

    @staticmethod
    def _detect_check_in(transcript: str) -> str | None:
        normalized = unicodedata.normalize("NFD", transcript.lower())
        normalized = "".join(character for character in normalized if not unicodedata.combining(character))
        if re.search(r"\b(me escuchas|me oyes|estas ahi)\b", normalized):
            return "Sí, te escucho."
        if re.search(r"\b(can you hear me|do you hear me|are you there)\b", normalized):
            return "Yes, I can hear you."
        return None

    @staticmethod
    def _detect_time_request(transcript: str) -> str | None:
        normalized = unicodedata.normalize("NFD", transcript.lower())
        normalized = "".join(character for character in normalized if not unicodedata.combining(character))
        if re.search(r"\b(que hora es|que ahora es|dime la hora|hora actual)\b", normalized):
            return f"Son las {datetime.now():%H:%M}."
        if re.search(r"\b(what time is it|tell me the time|current time)\b", normalized):
            return f"It's {datetime.now():%I:%M %p}.".replace(" 0", " ").lstrip("0")
        return None

    @staticmethod
    def _extract_text_to_type(transcript: str) -> str | None:
        match = re.match(
            r"^\s*(?:(?:por favor|please)\s+)?(?:escribe|escribir|teclea|teclear|tipea|type|write|enter)\s*:?\s+(.+?)\s*$",
            transcript,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip() if match else None

    @staticmethod
    def _run_system_action(
        action: SystemAction,
        *,
        allow_system_commands: bool,
        allow_navigation: bool,
    ) -> AssistantResponse:
        if action == "browser" and not allow_navigation:
            return AssistantResponse(
                "La navegación está desactivada. Activa su permiso para abrir el navegador.",
                "local",
            )
        if action != "browser" and not allow_system_commands:
            return AssistantResponse(
                "Los comandos están desactivados. Activa su permiso para abrir aplicaciones.",
                "local",
            )
        return AssistantResponse(execute_system_action(action), "local")

    def _get_ollama_client(self) -> Any:
        if self._ollama_client is None:
            import ollama

            self._ollama_client = ollama.Client(host=self._ollama_host)
        return self._ollama_client

    def _get_gemini_client(self) -> Any | None:
        if self._gemini_client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                return None

            from google import genai
            from google.genai import types

            self._gemini_client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=10_000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        return self._gemini_client

    def _respond_with_gemini_or_local(self, transcript: str) -> AssistantResponse:
        try:
            response = self._respond_with_gemini(transcript)
            if not response.startswith("El cerebro de la nube está desconectado"):
                return AssistantResponse(response, "gemini")
            reason = "no hay credenciales"
        except Exception as error:
            reason = f"{type(error).__name__}: {str(error)[:180]}"

        print(f"Gemini no respondió ({reason}); usando Ollama local como respaldo.")
        try:
            return AssistantResponse(self._respond_with_ollama(transcript), "local")
        except Exception as error:
            print(f"Ollama tampoco pudo responder ({type(error).__name__}).")
            if re.search(r"\b(what|where|when|why|how|can|could|please)\b", transcript, flags=re.IGNORECASE):
                return AssistantResponse("I can't reach either response service right now.", "local")
            return AssistantResponse("No puedo conectar con los servicios de respuesta ahora mismo.", "local")

    def _classify(self, transcript: str) -> RouteDecision:
        response = self._get_ollama_client().chat(
            model=self._ollama_model,
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
            format="json",
            options={"temperature": 0},
        )
        content = response.message.content.strip()
        payload = json.loads(content)
        if not isinstance(payload, dict) or set(payload) != {"destino", "tipo_accion", "accion"}:
            raise ValueError("Ollama devolvió una clasificación con estructura inválida.")

        destino = payload["destino"]
        tipo_accion = payload["tipo_accion"]
        accion = payload["accion"]
        if destino not in ("local", "nube"):
            raise ValueError("Ollama devolvió un destino no permitido.")
        if tipo_accion not in ("comando_sistema", "charla_rapida", "consulta_compleja"):
            raise ValueError("Ollama devolvió un tipo de acción no permitido.")
        if accion not in (None, "browser", "notepad", "explorer"):
            raise ValueError("Ollama devolvió una acción de sistema no permitida.")
        if (destino, tipo_accion) not in {
            ("local", "comando_sistema"),
            ("local", "charla_rapida"),
            ("nube", "consulta_compleja"),
        }:
            raise ValueError("Ollama devolvió una combinación de ruta y acción inválida.")
        if (tipo_accion == "comando_sistema") != (accion is not None):
            raise ValueError("Ollama devolvió una acción inconsistente con su clasificación.")
        return RouteDecision(
            destino=cast(Destination, destino),
            tipo_accion=cast(ActionType, tipo_accion),
            accion=cast(SystemAction | None, accion),
        )

    def _respond_with_ollama(self, transcript: str) -> str:
        response = self._get_ollama_client().chat(
            model=self._ollama_model,
            messages=[
                {
                    "role": "system",
                    "content": "Responde en el mismo idioma que el usuario, español o inglés, con una frase breve y natural para ser dicha en voz alta. No afirmes que ejecutaste una acción real.",
                },
                {"role": "user", "content": transcript},
            ],
            options={"temperature": 0.3},
        )
        text = response.message.content.strip()
        if not text:
            raise RuntimeError("Ollama no devolvió una respuesta de texto.")
        return text

    def _respond_with_gemini(self, transcript: str) -> str:
        client = self._get_gemini_client()
        if client is None:
            return "El cerebro de la nube está desconectado por falta de credenciales."

        from google.genai import types

        result = client.models.generate_content(
            model=self._gemini_model,
            contents=transcript,
            config=types.GenerateContentConfig(
                system_instruction=GEMINI_SYSTEM_PROMPT,
                temperature=0.3,
            ),
        )
        response = (result.text or "").strip()
        if not response:
            raise RuntimeError("Gemini no devolvió una respuesta de texto.")
        return response