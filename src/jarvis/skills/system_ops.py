"""Allowlisted Windows application launch actions."""

from __future__ import annotations

import subprocess
from typing import Literal


SystemAction = Literal["browser", "notepad", "explorer"]

_ACTIONS: dict[SystemAction, tuple[str, str]] = {
    "browser": ('start "" msedge', "Navegador abierto."),
    "notepad": ('start "" notepad', "Bloc de notas abierto."),
    "explorer": ('start "" explorer', "Explorador abierto."),
}


def execute_system_action(action: str) -> str:
    """Execute one supported application launch and return a short result."""
    if action not in _ACTIONS:
        raise ValueError(f"Acción de sistema no permitida: {action}")

    command, confirmation = _ACTIONS[action]
    try:
        subprocess.run(
            command,
            shell=True,
            check=True,
            timeout=5,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "No pude abrir la aplicación solicitada."
    return confirmation


def type_text(text: str) -> str:
    """Type explicitly requested text into the currently focused window."""
    text = text.strip()
    if not text:
        return "No recibí texto para escribir."
    if len(text) > 1000:
        return "El texto excede el límite de 1000 caracteres."

    import pyautogui

    pyautogui.typewrite(text, interval=0.01)
    return "Texto escrito."