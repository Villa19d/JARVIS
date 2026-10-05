"""CustomTkinter interface for the Jarvis desktop assistant."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

from jarvis.audio_engine import AudioEngine


class JarvisApp(ctk.CTk):
    """Owns the UI and forwards audio-thread events to Tk's main loop."""

    def __init__(self) -> None:
        super().__init__()
        self.title("JARVIS | Asistente de escritorio")
        self.geometry("980x640")
        self.minsize(760, 520)
        self.configure(fg_color="#11151b")

        self._events: queue.Queue[tuple[str, str]] = queue.Queue()
        self._command_permission = threading.Event()
        self._navigation_permission = threading.Event()
        self._audio_engine = AudioEngine(
            self._events,
            command_permission=self._command_permission,
            navigation_permission=self._navigation_permission,
        )
        self._assistant_active = False
        self._stopping = False

        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_events)
        self._append_log("Interfaz iniciada. El motor de audio está apagado.")

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 18))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="JARVIS",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color="#eef3f8",
        )
        title.grid(row=0, column=0, sticky="w")
        self._status_label = ctk.CTkLabel(
            header,
            text="●  DESACTIVADO",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#8d98a6",
        )
        self._status_label.grid(row=0, column=1, sticky="e")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 28))
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, minsize=250)
        content.grid_rowconfigure(0, weight=1)

        console_panel = ctk.CTkFrame(
            content,
            fg_color="#191f27",
            corner_radius=8,
            border_width=1,
            border_color="#28313b",
        )
        console_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        console_panel.grid_columnconfigure(0, weight=1)
        console_panel.grid_rowconfigure(1, weight=1)

        console_title = ctk.CTkLabel(
            console_panel,
            text="CONSOLA DEL SISTEMA",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#aab5c1",
        )
        console_title.grid(row=0, column=0, sticky="w", padx=18, pady=(16, 10))

        self._console = ctk.CTkTextbox(
            console_panel,
            wrap="word",
            state="disabled",
            fg_color="#11161c",
            text_color="#d3dce5",
            border_width=1,
            border_color="#28313b",
            corner_radius=6,
            font=ctk.CTkFont(family="Cascadia Mono", size=12),
        )
        self._console.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))

        side_panel = ctk.CTkFrame(
            content,
            fg_color="#191f27",
            corner_radius=8,
            border_width=1,
            border_color="#28313b",
        )
        side_panel.grid(row=0, column=1, sticky="nsew")
        side_panel.grid_columnconfigure(0, weight=1)

        side_title = ctk.CTkLabel(
            side_panel,
            text="PERMISOS DE SISTEMA",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#aab5c1",
        )
        side_title.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 14))

        self._navigation_switch = ctk.CTkSwitch(
            side_panel,
            text="Permitir navegación",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            progress_color="#27a89a",
            command=self._on_navigation_permission_changed,
        )
        self._navigation_switch.grid(row=1, column=0, sticky="w", padx=18, pady=10)
        self._commands_switch = ctk.CTkSwitch(
            side_panel,
            text="Permitir ejecución\nde comandos",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            progress_color="#27a89a",
            command=self._on_command_permission_changed,
        )
        self._commands_switch.grid(row=2, column=0, sticky="w", padx=18, pady=10)

        self._power_button = ctk.CTkButton(
            side_panel,
            text="Encender asistente",
            command=self._toggle_assistant,
            height=44,
            corner_radius=6,
            fg_color="#168c80",
            hover_color="#11766c",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        )
        self._power_button.grid(row=3, column=0, sticky="ew", padx=18, pady=(28, 18))

        permissions_note = ctk.CTkLabel(
            side_panel,
            text="Controla apertura de apps y\nescritura en la ventana activa.",
            justify="left",
            wraplength=210,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#7f8b98",
        )
        permissions_note.grid(row=4, column=0, sticky="w", padx=18, pady=(0, 18))

    def _toggle_assistant(self) -> None:
        if self._stopping:
            return

        if self._assistant_active:
            self._audio_engine.stop()
            self._assistant_active = False
            self._stopping = True
            self._power_button.configure(text="Deteniendo...", state="disabled")
            self._status_label.configure(text="●  DETENIENDO", text_color="#e5b65c")
            self._append_log("Apagando asistente; espera a que termine la operación en curso...")
            return

        if not self._audio_engine.start():
            self._append_log("El motor de audio todavía está finalizando.")
            return

        self._set_active(True)
        self._append_log("Encendiendo asistente...")

    def _on_navigation_permission_changed(self) -> None:
        if self._navigation_switch.get():
            self._navigation_permission.set()
        else:
            self._navigation_permission.clear()

    def _on_command_permission_changed(self) -> None:
        if self._commands_switch.get():
            self._command_permission.set()
        else:
            self._command_permission.clear()

    def _set_active(self, active: bool) -> None:
        self._assistant_active = active
        if active:
            self._power_button.configure(
                text="Apagar asistente",
                state="normal",
                fg_color="#b5484a",
                hover_color="#963a3c",
            )
            self._status_label.configure(text="●  ACTIVO", text_color="#42c7a7")
        else:
            self._power_button.configure(
                text="Encender asistente",
                state="normal",
                fg_color="#168c80",
                hover_color="#11766c",
            )
            self._status_label.configure(text="●  DESACTIVADO", text_color="#8d98a6")

    def _drain_events(self) -> None:
        while True:
            try:
                event_type, message = self._events.get_nowait()
            except queue.Empty:
                break

            self._append_log(message)
            if event_type == "status" and message.startswith("Sistema en línea"):
                self._status_label.configure(text="●  ESCUCHANDO", text_color="#42c7a7")
            elif event_type == "error":
                self._stopping = False
                self._set_active(False)
                self._status_label.configure(text="●  ERROR", text_color="#f07c78")
            elif event_type == "stopped" and self._status_label.cget("text") != "●  ERROR":
                self._stopping = False
                self._set_active(False)

        self.after(100, self._drain_events)

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._console.configure(state="normal")
        self._console.insert(tk.END, f"[{timestamp}] {message}\n")
        self._console.see(tk.END)
        self._console.configure(state="disabled")

    def _on_close(self) -> None:
        self._audio_engine.stop()
        self.destroy()
