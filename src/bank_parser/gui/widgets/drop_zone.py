"""Widget zona de drop + botón para seleccionar archivos manualmente."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from bank_parser.gui.theme import (
    BG_ELEVATED,
    BORDER_ACCENT,
    FONT_BODY,
    FONT_SMALL,
    FONT_SUBTITLE,
    TEAL,
    TEAL_LT,
    TEXT_MUTED,
    TEXT_PRIMARY,
)


class DropZone(ctk.CTkFrame):
    """Frame que muestra una zona de arrastre y un botón de selección."""

    def __init__(
        self,
        master,
        on_files_added: Callable[[list[Path]], None],
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._on_files_added = on_files_added
        self._build()

    def _build(self) -> None:
        self.configure(
            border_width=2,
            border_color=BORDER_ACCENT,
            corner_radius=12,
            fg_color=BG_ELEVATED,
        )
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.grid(row=0, column=0, padx=28, pady=22)

        ctk.CTkLabel(
            inner,
            text="↑",
            font=("Segoe UI", 34, "bold"),
            text_color=TEAL,
        ).pack()

        ctk.CTkLabel(
            inner,
            text="Arrastra archivos aquí",
            font=FONT_SUBTITLE,
            text_color=TEXT_PRIMARY,
        ).pack(pady=(6, 0))

        ctk.CTkLabel(
            inner,
            text="PDF  ·  ZIP",
            font=FONT_SMALL,
            text_color=TEXT_MUTED,
        ).pack(pady=(3, 0))

        ctk.CTkButton(
            inner,
            text="Seleccionar archivos",
            font=FONT_BODY,
            width=170,
            height=34,
            fg_color=TEAL,
            hover_color=TEAL_LT,
            corner_radius=8,
            command=self._browse,
        ).pack(pady=(14, 0))

        self._register_dnd()

    def _register_dnd(self) -> None:
        try:
            from tkinterdnd2 import DND_FILES

            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

    def _on_drop(self, event) -> None:
        paths = self._parse_dnd_data(event.data)
        if paths:
            self._on_files_added(paths)

    @staticmethod
    def _parse_dnd_data(raw: str) -> list[Path]:
        """Parsea la cadena de rutas que entrega tkinterdnd2 en Windows."""
        paths: list[Path] = []
        raw = raw.strip()
        i = 0
        while i < len(raw):
            if raw[i] == "{":
                end = raw.index("}", i)
                paths.append(Path(raw[i + 1 : end]))
                i = end + 2
            else:
                j = i
                while j < len(raw) and raw[j] != " ":
                    j += 1
                token = raw[i:j].strip()
                if token:
                    paths.append(Path(token))
                i = j + 1
        return paths

    def _browse(self) -> None:
        files = filedialog.askopenfilenames(
            title="Seleccionar estados de cuenta",
            filetypes=[
                ("PDF y ZIP", "*.pdf *.zip"),
                ("PDF", "*.pdf"),
                ("ZIP", "*.zip"),
            ],
        )
        if files:
            self._on_files_added([Path(f) for f in files])
