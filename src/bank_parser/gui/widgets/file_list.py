"""Widget lista de archivos cargados con su estado y metadatos."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import customtkinter as ctk

from bank_parser.gui.app_state import AppState, FileEntry
from bank_parser.gui.theme import (
    BG_ELEVATED,
    BG_SURFACE,
    BORDER_DEFAULT,
    CRIMSON,
    FONT_BODY,
    FONT_SMALL,
    FONT_SUBTITLE,
    STATUS_COLORS,
    TEXT_MUTED,
    TEXT_SECONDARY,
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
        self._scroll = ctk.CTkScrollableFrame(
            self,
            height=180,
            fg_color=BG_SURFACE,
            border_width=1,
            border_color=BORDER_DEFAULT,
            corner_radius=8,
        )
        self._scroll.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self._scroll.grid_columnconfigure(0, weight=1)
        self.refresh()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(8, 4))
        ctk.CTkLabel(header, text="Archivos cargados", font=FONT_SUBTITLE).pack(side="left")
        ctk.CTkButton(
            header,
            text="Limpiar todo",
            font=FONT_SMALL,
            width=90,
            height=26,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_ELEVATED,
            command=self._clear_all,
        ).pack(side="right")

    def _clear_all(self) -> None:
        if not self._state.entries:
            return
        from tkinter import messagebox

        if not messagebox.askyesno("Confirmar", "¿Limpiar todos los archivos cargados?"):
            return
        self._state.clear()
        self.refresh()

    def refresh(self) -> None:
        """Re-renderiza la lista completa desde el estado."""
        for w in self._row_widgets:
            w.destroy()
        self._row_widgets.clear()

        if not self._state.entries:
            empty = ctk.CTkLabel(
                self._scroll,
                text="Ningún archivo cargado",
                font=FONT_BODY,
                text_color=TEXT_MUTED,
            )
            empty.grid(row=0, column=0, pady=20)
            self._row_widgets.append(empty)
            return

        for i, entry in enumerate(self._state.entries):
            row = self._make_row(entry, i)
            row.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
            self._row_widgets.append(row)

    def _make_row(self, entry: FileEntry, idx: int) -> ctk.CTkFrame:
        status_color = STATUS_COLORS.get(entry.status.value, TEXT_MUTED)
        row = ctk.CTkFrame(
            self._scroll,
            corner_radius=6,
            fg_color=BG_ELEVATED,
            border_width=1,
            border_color=BORDER_DEFAULT,
        )
        row.grid_columnconfigure(1, weight=1)

        # Status dot
        ctk.CTkLabel(
            row,
            text="●",
            font=("Segoe UI", 11),
            text_color=status_color,
            width=20,
        ).grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=8)

        # File name
        ctk.CTkLabel(
            row,
            text=entry.path.name,
            font=FONT_BODY,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=4, pady=(7, 1))

        # Metadata
        meta_parts: list[str] = []
        if entry.bank_display != "—":
            meta_parts.append(entry.bank_display)
        if entry.rfc_display != "(sin RFC)":
            meta_parts.append(f"RFC: {entry.rfc_display}")
        if entry.movement_count:
            meta_parts.append(f"{entry.movement_count} movs.")
        if entry.has_warnings:
            meta_parts.append("advertencias")
        if entry.error:
            meta_parts.append(f"Error: {entry.error[:55]}")

        meta_text = "  ·  ".join(meta_parts) if meta_parts else entry.status.value
        ctk.CTkLabel(
            row,
            text=meta_text,
            font=FONT_SMALL,
            text_color=TEXT_MUTED if not entry.error else CRIMSON,
            anchor="w",
        ).grid(row=1, column=1, sticky="w", padx=4, pady=(1, 7))

        # Delete button
        ctk.CTkButton(
            row,
            text="✕",
            width=28,
            height=28,
            font=FONT_SMALL,
            fg_color="transparent",
            text_color=TEXT_SECONDARY,
            hover_color=BG_ELEVATED,
            command=lambda p=entry.path: self._remove(p),
        ).grid(row=0, column=2, rowspan=2, padx=(4, 8))

        return row

    def _remove(self, path: Path) -> None:
        self._on_remove(path)
        self.refresh()
