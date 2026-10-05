"""On-demand screen descriptions using an in-memory screenshot and Gemini."""

from __future__ import annotations

from io import BytesIO
from typing import Any


GEMINI_SYSTEM_PROMPT = (
    "Eres Jarvis. Responde siempre en una sola oración corta y directa. "
    "Nunca uses listas ni formato Markdown. Sé conversacional y responde en el idioma del usuario, español o inglés."
)


def describe_screen(client: Any, model: str) -> str:
    """Capture the current screen in memory and ask Gemini to describe it."""
    from google.genai import types
    from PIL import ImageGrab

    screenshot = ImageGrab.grab()
    image_buffer = BytesIO()
    try:
        screenshot.save(image_buffer, format="PNG")
    finally:
        screenshot.close()

    image_part = types.Part.from_bytes(
        data=image_buffer.getvalue(),
        mime_type="image/png",
    )
    response = client.models.generate_content(
        model=model,
        contents=["Describe brevemente lo que aparece en esta captura de pantalla.", image_part],
        config=types.GenerateContentConfig(
            system_instruction=GEMINI_SYSTEM_PROMPT,
            temperature=0.2,
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini no devolvió una descripción de la pantalla.")
    return text