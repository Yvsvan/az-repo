"""Widget lista de archivos cargados con su estado y metadatos."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import customtkinter as ctk

from bank_parser.gui.app_state import AppState, FileEntry
from bank_parser.gui.theme import (
    FONT_BODY,
    FONT_SMALL,
    FONT_SUBTITLE,
    GRAY_TEXT,
    RED,
    STATUS_COLORS,
)


class FileListFrame(ctk.CTkFrame):
    """Muestra la lista de archivos cargados con su estado de procesamiento."""

    def __init__(
        self,
        master,
        state: AppState,
        on_remove: Callable[[Path], None],
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._state = state
        self._on_remove = on_remove
        self._row_widgets: list[ctk.CTkFrame] = []
        self._build_header()
        self._scroll = ctk.CTkScrollableFrame(self, height=180)
        self._scroll.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self._scroll.grid_columnconfigure(0, weight=1)
        self.refresh()

    # ------------------------------------------------------------------
    # construcción
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(4, 2))
        ctk.CTkLabel(header, text="Archivos cargados", font=FONT_SUBTITLE).pack(side="left")
        ctk.CTkButton(
            header,
            text="Limpiar todo",
            font=FONT_SMALL,
            width=90,
            height=24,
            fg_color="transparent",
            border_width=1,
            command=self._clear_all,
        ).pack(side="right")

    def _clear_all(self) -> None:
        self._state.clear()
        self.refresh()

    # ------------------------------------------------------------------
    # refresco
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Re-renderiza la lista completa desde el estado."""
        for w in self._row_widgets:
            w.destroy()
        self._row_widgets.clear()

        if not self._state.entries:
            empty = ctk.CTkLabel(
                self._scroll,
                text="(ningún archivo cargado)",
                font=FONT_BODY,
                text_color=GRAY_TEXT,
            )
            empty.grid(row=0, column=0, pady=16)
            self._row_widgets.append(empty)
            return

        for i, entry in enumerate(self._state.entries):
            row = self._make_row(entry, i)
            row.grid(row=i, column=0, sticky="ew", padx=2, pady=2)
            self._row_widgets.append(row)

    def _make_row(self, entry: FileEntry, idx: int) -> ctk.CTkFrame:
        color = STATUS_COLORS.get(entry.status.value, GRAY_TEXT)
        row = ctk.CTkFrame(self._scroll, corner_radius=6)
        row.grid_columnconfigure(1, weight=1)

        # Icono de estado
        ctk.CTkLabel(
            row,
            text=entry.status_icon,
            font=("Segoe UI", 16),
            text_color=color,
            width=28,
        ).grid(row=0, column=0, rowspan=2, padx=(8, 4), pady=6)

        # Nombre del archivo
        ctk.CTkLabel(
            row,
            text=entry.path.name,
            font=FONT_BODY,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=4)

        # Metadatos (banco, RFC, movimientos)
        meta_parts: list[str] = []
        if entry.bank_display != "—":
            meta_parts.append(entry.bank_display)
        if entry.rfc_display != "(sin RFC)":
            meta_parts.append(f"RFC: {entry.rfc_display}")
        if entry.movement_count:
            meta_parts.append(f"{entry.movement_count} movs")
        if entry.has_warnings:
            meta_parts.append("⚠ advertencias")
        if entry.error:
            meta_parts.append(f"Error: {entry.error[:60]}")

        meta_text = "  ·  ".join(meta_parts) if meta_parts else entry.status.value
        ctk.CTkLabel(
            row,
            text=meta_text,
            font=FONT_SMALL,
            text_color=GRAY_TEXT if not entry.error else RED,
            anchor="w",
        ).grid(row=1, column=1, sticky="w", padx=4)

        # Botón eliminar
        ctk.CTkButton(
            row,
            text="✕",
            width=24,
            height=24,
            font=FONT_SMALL,
            fg_color="transparent",
            hover_color="#444",
            command=lambda p=entry.path: self._remove(p),
        ).grid(row=0, column=2, rowspan=2, padx=(4, 8))

        return row

    def _remove(self, path: Path) -> None:
        self._on_remove(path)
        self.refresh()
