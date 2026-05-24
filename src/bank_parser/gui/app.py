"""Ventana principal de la aplicación.

Estructura:
  - Header (fijo)
  - CTkTabview con tres pestañas:
      1. Analizador Bancario  (parser de estados de cuenta)
      2. Descarga SAT         (descarga masiva de CFDIs)
      3. Configuracion        (ajustes de ambas funciones)
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import bank_parser
from bank_parser.config.settings import AppSettings
from bank_parser.core.exceptions import BankParserError
from bank_parser.core.pipeline import process_file
from bank_parser.core.schema import Statement
from bank_parser.exporters.excel import export_to_xlsx
from bank_parser.exporters.json_exporter import export_to_json
from bank_parser.gui.app_state import AppState, FileEntry, FileStatus
from bank_parser.gui.theme import (
    BLUE_DARK,
    BORDER_DEFAULT,
    FONT_BODY,
    FONT_SMALL,
    FONT_SUBTITLE,
    FONT_TITLE,
    GRAY_TEXT,
    GREEN_DARK,
    TEAL,
    YELLOW,
    apply_theme,
)
from bank_parser.gui.widgets.drop_zone import DropZone
from bank_parser.gui.widgets.file_list import FileListFrame
from bank_parser.gui.widgets.preview_table import PreviewTable
from bank_parser.gui.widgets.progress_log import ProgressLog
from bank_parser.updater.github_updater import UpdateInfo, check_for_update

_GITHUB_REPO = "Yvsvan/az-repo"


def launch_gui() -> int:
    """Punto de entrada de la GUI. Retorna el exit code (0 = OK)."""
    apply_theme()
    app = BankParserApp()
    app.mainloop()
    return 0


class BankParserApp(ctk.CTk):
    """Ventana principal.

    Compatibilidad DnD: hereda TkinterDnD.DnDWrapper si la librería está
    disponible (import en tiempo de ejecución para no romper tests headless).
    """

    _POLL_MS = 100

    def __init__(self) -> None:
        try:
            from tkinterdnd2 import TkinterDnD

            TkinterDnD.DnDWrapper.__init__(self)
            import tkinterdnd2

            self.TkdndVersion = tkinterdnd2._require(self)
            self._dnd_available = True
        except Exception:
            self._dnd_available = False

        super().__init__()

        self._settings = AppSettings.load()
        self._state = AppState()
        self._state.output_dir = Path(self._settings.bank.output_dir)
        self._result_queue: queue.Queue = queue.Queue()
        self._update_queue: queue.Queue = queue.Queue()

        self._setup_window()
        self._build_ui()

        if self._settings.bank.auto_update:
            self.after(2000, self._start_update_check)

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.title(f"Asistente Contable  v{bank_parser.__version__}")
        self.geometry("980x820")
        self.minsize(820, 680)
        try:
            _ico = Path(__file__).resolve().parent.parent.parent.parent / "build" / "icon.ico"
            if _ico.exists():
                self.iconbitmap(str(_ico))
        except Exception:
            pass
        self.grid_rowconfigure(0, weight=0)  # header
        self.grid_rowconfigure(1, weight=1)  # tabs
        self.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # UI principal
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._build_header()

        self._tabs = ctk.CTkTabview(self, anchor="nw")
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

        bank_frame = self._tabs.add("  Analizador Bancario  ")
        self._build_bank_tab(bank_frame)

        sat_frame = self._tabs.add("  Descarga SAT  ")
        self._build_sat_tab(sat_frame)

        settings_frame = self._tabs.add("  Configuracion  ")
        self._build_settings_tab(settings_frame)

    # ------------------------------------------------------------------
    # Header (compartido entre tabs)
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=BLUE_DARK, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Asistente Contable",
            font=FONT_TITLE,
            text_color="white",
        ).grid(row=0, column=0, padx=20, pady=(12, 10), sticky="w")

        ctk.CTkLabel(
            header,
            text=f"v{bank_parser.__version__}",
            font=FONT_SMALL,
            text_color=GRAY_TEXT,
        ).grid(row=0, column=1, padx=(0, 8), pady=(12, 10), sticky="e")

        self._update_btn = ctk.CTkButton(
            header,
            text="",
            font=FONT_SMALL,
            fg_color=YELLOW,
            text_color="#0F172A",
            width=160,
            height=28,
            corner_radius=14,
            command=self._on_update_click,
        )

        # Teal accent line beneath the header
        ctk.CTkFrame(header, fg_color=TEAL, height=2, corner_radius=0).grid(
            row=1, column=0, columnspan=3, sticky="ew"
        )

    # ------------------------------------------------------------------
    # Tab 1: Analizador Bancario
    # ------------------------------------------------------------------

    def _build_bank_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_rowconfigure(0, weight=0)
        parent.grid_rowconfigure(1, weight=0)
        parent.grid_rowconfigure(2, weight=1)
        parent.grid_rowconfigure(3, weight=0)
        parent.grid_rowconfigure(4, weight=0)
        parent.grid_columnconfigure(0, weight=1)
        self._bank_parent = parent

        self._build_drop_zone(parent)
        self._build_file_list(parent)
        self._build_log(parent)
        self._build_preview_toggle(parent)
        self._build_action_bar(parent)

    def _build_drop_zone(self, parent: ctk.CTkFrame) -> None:
        self._drop_zone = DropZone(parent, on_files_added=self._on_files_added)
        self._drop_zone.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))

    def _build_file_list(self, parent: ctk.CTkFrame) -> None:
        self._file_list = FileListFrame(parent, state=self._state, on_remove=self._on_remove_file)
        self._file_list.grid(row=1, column=0, sticky="ew", padx=12, pady=4)

    def _build_log(self, parent: ctk.CTkFrame) -> None:
        self._log = ProgressLog(parent)
        self._log.grid(row=2, column=0, sticky="nsew", padx=12, pady=4)

    def _build_preview_toggle(self, parent: ctk.CTkFrame) -> None:
        self._preview_visible = False
        self._preview_frame: PreviewTable | None = None

        toggle_bar = ctk.CTkFrame(parent, fg_color="transparent")
        toggle_bar.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 2))

        self._preview_btn = ctk.CTkButton(
            toggle_bar,
            text="▶  Mostrar vista previa",
            font=FONT_SMALL,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            height=26,
            command=self._toggle_preview,
        )
        self._preview_btn.pack(side="left")

        self._summary_lbl = ctk.CTkLabel(
            toggle_bar,
            text="",
            font=FONT_SMALL,
            text_color=GRAY_TEXT,
        )
        self._summary_lbl.pack(side="right")

    def _build_action_bar(self, parent: ctk.CTkFrame) -> None:
        bar = ctk.CTkFrame(parent, fg_color=BLUE_DARK, corner_radius=0)
        bar.grid(row=4, column=0, sticky="ew")
        bar.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(bar, text="Salida:", font=FONT_SMALL, text_color=GRAY_TEXT).grid(
            row=0, column=0, padx=(14, 4), pady=10
        )
        self._output_label = ctk.CTkLabel(
            bar,
            text=self._truncate_path(self._state.output_dir),
            font=FONT_SMALL,
            text_color="white",
            width=220,
            anchor="w",
            cursor="hand2",
        )
        self._output_label.grid(row=0, column=1, padx=0, pady=10, sticky="w")
        self._output_label.bind("<Button-1>", lambda _: self._open_output_folder())

        ctk.CTkButton(
            bar,
            text="…",
            width=32,
            height=28,
            font=FONT_BODY,
            command=self._choose_output_dir,
        ).grid(row=0, column=2, padx=(2, 12), pady=10, sticky="w")

        self._process_btn = ctk.CTkButton(
            bar,
            text="▶  Procesar",
            font=FONT_SUBTITLE,
            width=130,
            height=36,
            command=self._process_all,
        )
        self._process_btn.grid(row=0, column=3, padx=4, pady=10)

        self._xlsx_btn = ctk.CTkButton(
            bar,
            text="Exportar Excel",
            font=FONT_BODY,
            width=120,
            height=36,
            fg_color=GREEN_DARK,
            state="disabled",
            command=self._export_xlsx,
        )
        self._xlsx_btn.grid(row=0, column=4, padx=4, pady=10)

        self._json_btn = ctk.CTkButton(
            bar,
            text="Exportar JSON",
            font=FONT_BODY,
            width=120,
            height=36,
            fg_color="#5D4037",
            state="disabled",
            command=self._export_json,
        )
        self._json_btn.grid(row=0, column=5, padx=(4, 14), pady=10)

        # Progress bar — hidden until processing starts
        self._bank_progress = ctk.CTkProgressBar(
            bar,
            mode="indeterminate",
            height=4,
            progress_color=TEAL,
        )
        self._bank_progress.grid(row=1, column=0, columnspan=6, sticky="ew")
        self._bank_progress.grid_remove()

    # ------------------------------------------------------------------
    # Tab 2: Descarga SAT
    # ------------------------------------------------------------------

    def _build_sat_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        from bank_parser.gui.sat_tab import SatTab

        SatTab(parent, settings=self._settings).grid(row=0, column=0, sticky="nsew")

    # ------------------------------------------------------------------
    # Tab 3: Configuracion
    # ------------------------------------------------------------------

    def _build_settings_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        from bank_parser.gui.settings_tab import SettingsTab

        SettingsTab(parent, settings=self._settings).grid(row=0, column=0, sticky="nsew")

    # ------------------------------------------------------------------
    # Callbacks de archivos (bank parser)
    # ------------------------------------------------------------------

    def _on_files_added(self, paths: list[Path]) -> None:
        added = 0
        for p in paths:
            if p.suffix.lower() not in (".pdf", ".zip"):
                self._log.warn(f"Formato no soportado: {p.name}")
                continue
            entry = self._state.add_file(p)
            if entry is None:
                self._log.info(f"Ya cargado: {p.name}")
            else:
                self._log.info(f"Archivo cargado: {p.name}")
                added += 1
        if added:
            self._file_list.refresh()
            self._update_buttons()

    def _on_remove_file(self, path: Path) -> None:
        self._state.remove_file(path)
        self._update_buttons()

    # ------------------------------------------------------------------
    # Procesamiento (hilos de fondo)
    # ------------------------------------------------------------------

    def _process_all(self) -> None:
        pending = self._state.processable_entries
        if not pending:
            self._log.warn("No hay archivos pendientes de procesar.")
            return

        self._process_btn.configure(state="disabled")
        self._bank_progress.grid()
        self._bank_progress.start()
        self._log.info(f"Procesando {len(pending)} archivo(s)…")

        for entry in pending:
            entry.status = FileStatus.PROCESSING
            self._file_list.refresh()
            threading.Thread(target=self._worker, args=(entry,), daemon=True).start()

        self.after(self._POLL_MS, self._poll_results)

    def _worker(self, entry: FileEntry) -> None:
        try:
            statements = process_file(entry.path)
            self._result_queue.put(("ok", entry, statements))
        except BankParserError as exc:
            self._result_queue.put(("error", entry, str(exc)))
        except Exception as exc:
            self._result_queue.put(("error", entry, f"Error inesperado: {exc}"))

    def _poll_results(self) -> None:
        try:
            while True:
                kind, entry, payload = self._result_queue.get_nowait()
                if kind == "ok":
                    self._handle_ok(entry, payload)
                else:
                    self._handle_error(entry, payload)
        except queue.Empty:
            pass

        if self._state.is_processing:
            self.after(self._POLL_MS, self._poll_results)
        else:
            self._on_processing_done()

    def _handle_ok(self, entry: FileEntry, statements: list[Statement]) -> None:
        entry.statements = statements
        if entry.has_warnings:
            entry.status = FileStatus.WARNING
            for stmt in statements:
                for w in stmt.warnings:
                    self._log.warn(f"{entry.path.name}: {w}")
        else:
            entry.status = FileStatus.OK

        level = "warn" if entry.has_warnings else "ok"
        self._log.log(
            f"{entry.path.name} → {entry.bank_display} | RFC: {entry.rfc_display} | {entry.movement_count} movimientos",
            level,
        )
        self._file_list.refresh()

    def _handle_error(self, entry: FileEntry, msg: str) -> None:
        entry.status = FileStatus.ERROR
        entry.error = msg
        self._log.error(f"{entry.path.name}: {msg}")
        self._file_list.refresh()

    def _on_processing_done(self) -> None:
        self._bank_progress.stop()
        self._bank_progress.grid_remove()
        self._process_btn.configure(state="normal")
        self._update_buttons()

        ok = sum(1 for e in self._state.entries if e.status == FileStatus.OK)
        warn = sum(1 for e in self._state.entries if e.status == FileStatus.WARNING)
        err = sum(1 for e in self._state.entries if e.status == FileStatus.ERROR)
        parts = [f"{ok + warn} procesados"]
        if warn:
            parts.append(f"{warn} advertencias")
        if err:
            parts.append(f"{err} errores")
        self._summary_lbl.configure(text=" · ".join(parts))

        self._log.info(f"Procesamiento completo. {ok + warn} archivo(s) listos para exportar.")
        if self._preview_visible and self._preview_frame:
            self._preview_frame.load(self._state.all_statements)

    # ------------------------------------------------------------------
    # Exportación
    # ------------------------------------------------------------------

    def _export_xlsx(self) -> None:
        if not self._state.can_export:
            return
        dest = self._state.output_dir / "estados_de_cuenta.xlsx"
        try:
            path = export_to_xlsx(self._state.all_statements, dest)
            self._log.ok(f"Excel exportado → {path}")
            messagebox.showinfo("Exportación exitosa", f"Archivo guardado en:\n{path}")
        except Exception as exc:
            self._log.error(f"Error al exportar Excel: {exc}")
            messagebox.showerror("Error de exportación", str(exc))

    def _export_json(self) -> None:
        if not self._state.can_export:
            return
        dest = self._state.output_dir / "estados_de_cuenta.json"
        try:
            path = export_to_json(self._state.all_statements, dest)
            self._log.ok(f"JSON exportado → {path}")
            messagebox.showinfo("Exportación exitosa", f"Archivo guardado en:\n{path}")
        except Exception as exc:
            self._log.error(f"Error al exportar JSON: {exc}")
            messagebox.showerror("Error de exportación", str(exc))

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _toggle_preview(self) -> None:
        if self._preview_visible:
            if self._preview_frame:
                self._preview_frame.grid_forget()
                self._preview_frame.destroy()
                self._preview_frame = None
            self._log.grid(row=2, column=0, sticky="nsew", padx=12, pady=4)
            self._preview_visible = False
            self._preview_btn.configure(text="▶  Mostrar vista previa")
        else:
            self._log.grid_forget()
            self._preview_frame = PreviewTable(self._bank_parent)
            self._preview_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=4)
            self._preview_frame.load(self._state.all_statements)
            self._preview_visible = True
            self._preview_btn.configure(text="▼  Ocultar vista previa")

    # ------------------------------------------------------------------
    # Auto-update
    # ------------------------------------------------------------------

    def _start_update_check(self) -> None:
        threading.Thread(target=self._update_worker, daemon=True).start()
        self.after(500, self._poll_update_result)

    def _update_worker(self) -> None:
        info = check_for_update(_GITHUB_REPO, bank_parser.__version__)
        self._update_queue.put(info)

    def _poll_update_result(self) -> None:
        try:
            info = self._update_queue.get_nowait()
            if info is not None:
                self._show_update_banner(info)
        except queue.Empty:
            self.after(500, self._poll_update_result)

    def _show_update_banner(self, info: UpdateInfo) -> None:
        self._pending_update = info
        self._update_btn.configure(text=f"↻ {info.latest} disponible")
        self._update_btn.grid(row=0, column=2, padx=(0, 12), pady=10, sticky="e")
        self._log.info(f"Actualización disponible: v{info.latest} (tienes v{info.current})")

    def _on_update_click(self) -> None:
        if not hasattr(self, "_pending_update"):
            return
        from bank_parser.gui.widgets.update_dialog import UpdateDialog

        UpdateDialog(self, self._pending_update)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _open_output_folder(self) -> None:
        import os

        try:
            os.startfile(str(self._state.output_dir))
        except Exception:
            pass

    def _choose_output_dir(self) -> None:
        d = filedialog.askdirectory(
            title="Seleccionar carpeta de salida", initialdir=self._state.output_dir
        )
        if d:
            self._state.output_dir = Path(d)
            self._settings.bank.output_dir = d
            self._settings.save()
            self._output_label.configure(text=self._truncate_path(self._state.output_dir))

    def _update_buttons(self) -> None:
        can = self._state.can_export
        self._xlsx_btn.configure(state="normal" if can else "disabled")
        self._json_btn.configure(state="normal" if can else "disabled")
        self._process_btn.configure(state="normal" if self._state.has_files else "disabled")

    @staticmethod
    def _truncate_path(p: Path, max_len: int = 38) -> str:
        s = str(p)
        return s if len(s) <= max_len else "…" + s[-(max_len - 1) :]
