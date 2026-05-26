"""Widget de log de progreso con timestamp y colores por nivel."""

from __future__ import annotations

import re
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

# Messages like "[AUAI000504PN6/Emitidos] ..." are updated in-place per key.
_RFC_LABEL_RE = re.compile(r"^\[([A-Z0-9]+/\w+)\]")


class ProgressLog(ctk.CTkFrame):
    """Área de texto scrollable que registra el progreso del pipeline."""

    _TAG_OK = "ok"
    _TAG_WARN = "warn"
    _TAG_ERROR = "error"
    _TAG_INFO = "info"

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._live_marks: dict[str, str] = {}  # "[RFC/label]" → tk mark name
        self._mark_seq = 0
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
        tw = self._text._textbox

        # Info messages with an [RFC/label] prefix update their row in-place
        # so polling "Procesando…" lines don't flood the log.
        if level == "info":
            m = _RFC_LABEL_RE.match(message)
            if m:
                key = m.group(1)
                self._text.configure(state="normal")
                if key in self._live_marks:
                    mark = self._live_marks[key]
                    try:
                        # Get the row number BEFORE any modification
                        row = tw.index(mark).split(".")[0]
                        tw.delete(f"{row}.0", f"{row}.0 lineend +1c")
                        tw.insert(f"{row}.0", line, tag)
                        # Reset mark explicitly — left-gravity drift after delete
                        tw.mark_set(mark, f"{row}.0")
                        self._text.configure(state="disabled")
                        tw.see("end")
                        return
                    except Exception:
                        del self._live_marks[key]
                # First occurrence: record row, insert, plant mark at row start
                self._mark_seq += 1
                mark = f"_live{self._mark_seq}"
                row = tw.index("end").split(".")[0]
                tw.insert("end", line, tag)
                tw.mark_set(mark, f"{row}.0")
                tw.mark_gravity(mark, "left")
                self._live_marks[key] = mark
                self._text.configure(state="disabled")
                tw.see("end")
                return

        self._text.configure(state="normal")
        tw.insert("end", line, tag)
        self._text.configure(state="disabled")
        tw.see("end")

    def clear(self) -> None:
        self._live_marks.clear()
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
