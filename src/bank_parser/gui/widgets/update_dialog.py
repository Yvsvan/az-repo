"""Diálogo de actualización con barra de progreso de descarga."""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path

import customtkinter as ctk

from bank_parser.gui.theme import (
    BG_ELEVATED,
    BG_SURFACE,
    BORDER_DEFAULT,
    CRIMSON,
    EMERALD,
    FONT_BODY,
    FONT_SMALL,
    FONT_SUBTITLE,
    GRAY_TEXT,
    TEAL,
    TEXT_SECONDARY,
    YELLOW,
)


class UpdateDialog(ctk.CTkToplevel):
    """Muestra info de la nueva versión y maneja la descarga + instalación."""

    def __init__(self, master, info) -> None:
        super().__init__(master)
        self.title("Actualización disponible")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self._info = info
        self._q: queue.Queue = queue.Queue()
        self._zip_path: Path | None = None
        self._build()
        self.after(80, self._grab_focus)

    def _grab_focus(self) -> None:
        self.grab_set()
        self.focus_force()

    def _build(self) -> None:
        self.configure(fg_color=BG_SURFACE)
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(padx=24, pady=20, fill="both", expand=True)

        # Version banner
        banner = ctk.CTkFrame(f, fg_color=BG_ELEVATED, corner_radius=8)
        banner.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(
            banner,
            text=f"Nueva versión: {self._info.latest}",
            font=FONT_SUBTITLE,
            text_color=YELLOW,
        ).pack(pady=(10, 2))
        ctk.CTkLabel(
            banner,
            text=f"Versión instalada: {self._info.current}",
            font=FONT_SMALL,
            text_color=TEXT_SECONDARY,
        ).pack(pady=(0, 10))

        # Status label
        self._status_lbl = ctk.CTkLabel(
            f,
            text="Listo para descargar e instalar.",
            font=FONT_SMALL,
            text_color=GRAY_TEXT,
        )
        self._status_lbl.pack(pady=(0, 8))

        # Progress bar (hidden initially)
        self._progress = ctk.CTkProgressBar(
            f, mode="determinate", width=320, height=8, progress_color=TEAL
        )
        self._progress.set(0)
        self._progress.pack(pady=(0, 12))
        self._progress.pack_forget()

        # Buttons
        btn_row = ctk.CTkFrame(f, fg_color="transparent")
        btn_row.pack(fill="x")

        ctk.CTkButton(
            btn_row,
            text="Cancelar",
            font=FONT_SMALL,
            width=100,
            height=32,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_ELEVATED,
            command=self.destroy,
        ).pack(side="left")

        self._install_btn = ctk.CTkButton(
            btn_row,
            text="⬇  Descargar e instalar",
            font=FONT_BODY,
            width=200,
            height=32,
            fg_color=TEAL,
            command=self._start_download,
        )
        self._install_btn.pack(side="right")

        ctk.CTkButton(
            btn_row,
            text="Ver release",
            font=FONT_SMALL,
            width=100,
            height=32,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_ELEVATED,
            command=lambda: self._open_browser(),
        ).pack(side="right", padx=(0, 8))

    def _open_browser(self) -> None:
        from bank_parser.updater.github_updater import open_release_page

        open_release_page(self._info)

    def _start_download(self) -> None:
        self._install_btn.configure(state="disabled", text="Descargando…")
        self._progress.set(0)
        self._progress.pack(pady=(0, 12))
        self._status_lbl.configure(text="Descargando actualización…", text_color=GRAY_TEXT)
        threading.Thread(target=self._download_worker, daemon=True).start()
        self.after(100, self._poll)

    def _download_worker(self) -> None:
        from bank_parser.updater.github_updater import download_release

        def on_progress(downloaded: int, total: int) -> None:
            if total:
                self._q.put(("progress", downloaded / total))

        zip_path = download_release(self._info, progress_callback=on_progress)
        if zip_path:
            self._q.put(("done", zip_path))
        else:
            self._q.put(("error", "No se pudo descargar la actualización."))

    def _poll(self) -> None:
        try:
            while True:
                item = self._q.get_nowait()
                if item[0] == "progress":
                    self._progress.set(item[1])
                elif item[0] == "done":
                    self._zip_path = item[1]
                    self._on_download_done()
                    return
                elif item[0] == "error":
                    self._on_error(item[1])
                    return
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _on_download_done(self) -> None:
        self._progress.set(1)
        self._status_lbl.configure(
            text="Descarga completa. La aplicación se cerrará y reiniciará.",
            text_color=EMERALD,
        )
        self._install_btn.configure(
            text="Instalar y reiniciar",
            state="normal",
            command=self._apply,
        )

    def _on_error(self, msg: str) -> None:
        self._status_lbl.configure(text=msg, text_color=CRIMSON)
        self._install_btn.configure(
            text="Ver release en GitHub",
            state="normal",
            command=self._open_browser,
        )

    def _apply(self) -> None:
        from bank_parser.updater.github_updater import apply_update, open_release_page

        self._install_btn.configure(state="disabled", text="Aplicando…")
        self._status_lbl.configure(text="Preparando reinicio…", text_color=GRAY_TEXT)

        launched = self._zip_path and apply_update(self._zip_path)
        if launched:
            # Give tkinter a moment to paint, then exit cleanly
            self.after(400, lambda: sys.exit(0))
        else:
            # Not a frozen bundle — fall back to browser
            self._status_lbl.configure(
                text="Descarga manual requerida. Abriendo página del release…",
                text_color=GRAY_TEXT,
            )
            open_release_page(self._info)
            self.destroy()
