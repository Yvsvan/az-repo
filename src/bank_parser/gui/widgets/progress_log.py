"""Widget de log de progreso con timestamp y colores por nivel."""

from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

from bank_parser.gui.theme import (
    AMBER,
    BG_ELEVATED,
    BG_INPUT,
    BORDER_DEFAULT,
    CRIMSON,
    EMERALD,
    FONT_MONO,
    FONT_SMALL,
    FONT_SUBTITLE,
    TEXT_SECONDARY,
)


class ProgressLog(ctk.CTkFrame):
    """Área de texto scrollable que registra el progreso del pipeline."""

    _TAG_OK = "ok"
    _TAG_WARN = "warn"
    _TAG_ERROR = "error"
    _TAG_INFO = "info"

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._build()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(8, 4))
        ctk.CTkLabel(header, text="Log de actividad", font=FONT_SUBTITLE).pack(side="left")
        ctk.CTkButton(
            header,
            text="Limpiar",
            font=FONT_SMALL,
            width=70,
            height=26,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_ELEVATED,
            command=self.clear,
        ).pack(side="right")

        self._text = ctk.CTkTextbox(
            self,
            font=FONT_MONO,
            height=160,
            state="disabled",
            wrap="word",
            fg_color=BG_INPUT,
            border_width=1,
            border_color=BORDER_DEFAULT,
            corner_radius=8,
        )
        self._text.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        tk_widget = self._text._textbox
        tk_widget.tag_config(self._TAG_OK, foreground=EMERALD)
        tk_widget.tag_config(self._TAG_WARN, foreground=AMBER)
        tk_widget.tag_config(self._TAG_ERROR, foreground=CRIMSON)
        tk_widget.tag_config(self._TAG_INFO, foreground=TEXT_SECONDARY)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def log(self, message: str, level: str = "info") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}\n"
        tag = level if level in (self._TAG_OK, self._TAG_WARN, self._TAG_ERROR) else self._TAG_INFO

        self._text.configure(state="normal")
        self._text._textbox.insert("end", line, tag)
        self._text.configure(state="disabled")
        self._text._textbox.see("end")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")

    def ok(self, msg: str) -> None:
        self.log(f"✓ {msg}", "ok")

    def warn(self, msg: str) -> None:
        self.log(f"! {msg}", "warn")

    def error(self, msg: str) -> None:
        self.log(f"✗ {msg}", "error")

    def info(self, msg: str) -> None:
        self.log(f"  {msg}", "info")
