"""Widget zona de drop + botón para seleccionar archivos manualmente."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from bank_parser.gui.theme import BLUE_MID, FONT_BODY, FONT_SUBTITLE, GRAY_TEXT


class DropZone(ctk.CTkFrame):
    """Frame que muestra una zona de arrastre y un botón de selección.

    Requiere que la ventana raíz ya haya registrado TkinterDnD
    (lo hace :class:`~bank_parser.gui.app.BankParserApp`).
    """

    def __init__(
        self,
        master,
        on_files_added: Callable[[list[Path]], None],
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._on_files_added = on_files_added
        self._build()

    # ------------------------------------------------------------------
    # construcción
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.configure(
            border_width=2,
            border_color=BLUE_MID,
            corner_radius=12,
            fg_color="transparent",
        )
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.grid(row=0, column=0, padx=20, pady=20)

        ctk.CTkLabel(
            inner,
            text="📄",
            font=("Segoe UI", 40),
        ).pack()

        ctk.CTkLabel(
            inner,
            text="Suelta tus PDFs o ZIPs aquí",
            font=FONT_SUBTITLE,
        ).pack(pady=(4, 0))

        ctk.CTkLabel(
            inner,
            text="(o haz clic para seleccionar archivos)",
            font=FONT_BODY,
            text_color=GRAY_TEXT,
        ).pack()

        ctk.CTkButton(
            inner,
            text="Seleccionar archivos…",
            font=FONT_BODY,
            command=self._browse,
        ).pack(pady=(12, 0))

        # Registrar drag-and-drop si TkinterDnD está disponible
        self._register_dnd()

    # ------------------------------------------------------------------
    # drag-and-drop
    # ------------------------------------------------------------------

    def _register_dnd(self) -> None:
        try:
            from tkinterdnd2 import DND_FILES

            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass  # Sin tkinterdnd2 el botón manual sigue funcionando

    def _on_drop(self, event) -> None:
        raw: str = event.data
        # tkinterdnd2 envuelve rutas con espacios en llaves: {/path/with spaces/}
        paths = self._parse_dnd_data(raw)
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
                # Busca el siguiente espacio que no sea parte de una ruta entre {}
                j = i
                while j < len(raw) and raw[j] != " ":
                    j += 1
                token = raw[i:j].strip()
                if token:
                    paths.append(Path(token))
                i = j + 1
        return paths

    # ------------------------------------------------------------------
    # diálogo manual
    # ------------------------------------------------------------------

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
