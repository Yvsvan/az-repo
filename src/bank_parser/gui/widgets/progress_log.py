"""Widget de log de progreso con timestamp y colores por nivel."""

from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

from bank_parser.gui.theme import FONT_MONO, FONT_SUBTITLE, GRAY_TEXT, GREEN, RED, YELLOW


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
        header.pack(fill="x", padx=4, pady=(4, 2))
        ctk.CTkLabel(header, text="Log de progreso", font=FONT_SUBTITLE).pack(side="left")
        ctk.CTkButton(
            header,
            text="Limpiar",
            font=("Segoe UI", 10),
            width=70,
            height=24,
            fg_color="transparent",
            border_width=1,
            command=self.clear,
        ).pack(side="right")

        # CTkTextbox es scrollable por sí mismo
        self._text = ctk.CTkTextbox(
            self,
            font=FONT_MONO,
            height=160,
            state="disabled",
            wrap="word",
        )
        self._text.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # Configurar tags de color en el widget subyacente de tk
        tk_widget = self._text._textbox
        tk_widget.tag_config(self._TAG_OK, foreground=GREEN)
        tk_widget.tag_config(self._TAG_WARN, foreground=YELLOW)
        tk_widget.tag_config(self._TAG_ERROR, foreground=RED)
        tk_widget.tag_config(self._TAG_INFO, foreground=GRAY_TEXT)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def log(self, message: str, level: str = "info") -> None:
        """Agrega una línea al log con timestamp.

        Args:
            message: Texto a mostrar.
            level: ``"info"``, ``"ok"``, ``"warn"`` o ``"error"``.
        """
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

    # Atajos semánticos
    def ok(self, msg: str) -> None:
        self.log(f"✓ {msg}", "ok")

    def warn(self, msg: str) -> None:
        self.log(f"⚠ {msg}", "warn")

    def error(self, msg: str) -> None:
        self.log(f"✗ {msg}", "error")

    def info(self, msg: str) -> None:
        self.log(f"  {msg}", "info")
