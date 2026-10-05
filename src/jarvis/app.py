"""Application entry point."""

from pathlib import Path

import customtkinter as ctk
from dotenv import load_dotenv

from jarvis.gui import JarvisApp


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    dotenv_path = project_root / ".env"
    if not dotenv_path.is_file():
        dotenv_path = project_root / "src" / ".env"
    if dotenv_path.is_file():
        load_dotenv(dotenv_path)
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("dark-blue")
    app = JarvisApp()
    app.mainloop()


if __name__ == "__main__":
    main()
