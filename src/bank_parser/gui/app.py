"""Ventana principal de la aplicación.

Integra todos los widgets y el pipeline de procesamiento.
El pipeline corre en hilos de fondo para no bloquear la UI.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import bank_parser
from bank_parser.core.exceptions import BankParserError
from bank_parser.core.pipeline import process_file
from bank_parser.core.schema import Statement
from bank_parser.exporters.excel import export_to_xlsx
from bank_parser.exporters.json_exporter import export_to_json
from bank_parser.gui.app_state import AppState, FileEntry, FileStatus
from bank_parser.gui.theme import (
    BLUE_DARK,
    FONT_BODY,
    FONT_SMALL,
    FONT_SUBTITLE,
    FONT_TITLE,
    GRAY_TEXT,
    GREEN_DARK,
    YELLOW,
    apply_theme,
)
from bank_parser.gui.widgets.drop_zone import DropZone
from bank_parser.gui.widgets.file_list import FileListFrame
from bank_parser.gui.widgets.preview_table import PreviewTable
from bank_parser.gui.widgets.progress_log import ProgressLog
from bank_parser.updater.github_updater import UpdateInfo, check_for_update, open_release_page

# Repositorio de GitHub para consultar updates (cambiar al repo real)
_GITHUB_REPO = "ivan-aguilera/az-repo"


def launch_gui() -> int:
    """Punto de entrada de la GUI. Retorna el exit code (0 = OK)."""
    apply_theme()
    app = BankParserApp()
    app.mainloop()
    return 0


class BankParserApp(ctk.CTk):
    """Ventana principal del parser de estados de cuenta.

    Compatibilidad drag-and-drop: hereda TkinterDnD.DnDWrapper cuando
    la librería está disponible (en tiempo de ejecución, no en tiempo de
    importación para no romper tests headless).
    """

    _POLL_MS = 100  # ms entre checks de la cola de resultados

    def __init__(self) -> None:
        # Activar DnD si la librería está disponible
        try:
            from tkinterdnd2 import TkinterDnD

            TkinterDnD.DnDWrapper.__init__(self)
            # Inyectar TkdndVersion en la instancia para que los widgets
            # hijos puedan registrarse como drop targets
            import tkinterdnd2

            self.TkdndVersion = tkinterdnd2._require(self)
            self._dnd_available = True
        except Exception:
            self._dnd_available = False

        super().__init__()

        self._state = AppState()
        self._result_queue: queue.Queue = queue.Queue()
        self._update_queue: queue.Queue = queue.Queue()

        self._setup_window()
        self._build_ui()

        # Iniciar check de updates en segundo plano 2 s después del arranque
        self.after(2000, self._start_update_check)

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.title(f"Parser de Estados de Cuenta Bancarios  v{bank_parser.__version__}")
        self.geometry("860x780")
        self.minsize(720, 640)
        # Ícono de la ventana (opcional — falla silenciosamente si el .ico no existe)
        try:
            _ico = Path(__file__).resolve().parent.parent.parent.parent / "build" / "icon.ico"
            if _ico.exists():
                self.iconbitmap(str(_ico))
        except Exception:
            pass
        self.grid_rowconfigure(0, weight=0)  # header
        self.grid_rowconfigure(1, weight=0)  # drop zone
        self.grid_rowconfigure(2, weight=0)  # file list
        self.grid_rowconfigure(3, weight=1)  # log
        self.grid_rowconfigure(4, weight=0)  # preview toggle
        self.grid_rowconfigure(5, weight=0)  # action bar
        self.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # construcción de la UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._build_header()
        self._build_drop_zone()
        self._build_file_list()
        self._build_log()
        self._build_preview_toggle()
        self._build_action_bar()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=BLUE_DARK, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="🏦  Parser de Estados de Cuenta Bancarios",
            font=FONT_TITLE,
            text_color="white",
        ).grid(row=0, column=0, padx=16, pady=10, sticky="w")

        ctk.CTkLabel(
            header,
            text=f"v{bank_parser.__version__}",
            font=FONT_SMALL,
            text_color=GRAY_TEXT,
        ).grid(row=0, column=1, padx=(0, 8), pady=10, sticky="e")

        # Botón de actualización (oculto hasta que haya update disponible)
        self._update_btn = ctk.CTkButton(
            header,
            text="",
            font=FONT_SMALL,
            fg_color=YELLOW,
            text_color="#1a1a1a",
            width=160,
            height=28,
            command=self._on_update_click,
        )
        # Se hace visible sólo cuando hay update; columna 2 reservada

    def _build_drop_zone(self) -> None:
        self._drop_zone = DropZone(
            self,
            on_files_added=self._on_files_added,
        )
        self._drop_zone.grid(row=1, column=0, sticky="ew", padx=12, pady=(10, 4))

    def _build_file_list(self) -> None:
        self._file_list = FileListFrame(
            self,
            state=self._state,
            on_remove=self._on_remove_file,
        )
        self._file_list.grid(row=2, column=0, sticky="ew", padx=12, pady=4)

    def _build_log(self) -> None:
        self._log = ProgressLog(self)
        self._log.grid(row=3, column=0, sticky="nsew", padx=12, pady=4)

    def _build_preview_toggle(self) -> None:
        """Botón para mostrar/ocultar la tabla de movimientos."""
        self._preview_visible = False
        self._preview_frame: PreviewTable | None = None

        toggle_bar = ctk.CTkFrame(self, fg_color="transparent")
        toggle_bar.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 2))

        self._preview_btn = ctk.CTkButton(
            toggle_bar,
            text="▶  Mostrar vista previa de movimientos",
            font=FONT_SMALL,
            fg_color="transparent",
            border_width=1,
            height=26,
            command=self._toggle_preview,
        )
        self._preview_btn.pack(side="left")

    def _build_action_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=BLUE_DARK, corner_radius=0)
        bar.grid(row=5, column=0, sticky="ew")
        bar.grid_columnconfigure(2, weight=1)

        # Carpeta de salida
        ctk.CTkLabel(bar, text="Salida:", font=FONT_SMALL, text_color=GRAY_TEXT).grid(
            row=0, column=0, padx=(12, 4), pady=10
        )

        self._output_label = ctk.CTkLabel(
            bar,
            text=self._truncate_path(self._state.output_dir),
            font=FONT_SMALL,
            text_color="white",
            width=220,
            anchor="w",
        )
        self._output_label.grid(row=0, column=1, padx=0, pady=10, sticky="w")

        ctk.CTkButton(
            bar,
            text="📁",
            width=32,
            height=28,
            font=FONT_BODY,
            command=self._choose_output_dir,
        ).grid(row=0, column=2, padx=(2, 12), pady=10, sticky="w")

        # Botones de acción
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
            text="📊 Exportar .xlsx",
            font=FONT_BODY,
            width=130,
            height=36,
            fg_color=GREEN_DARK,
            state="disabled",
            command=self._export_xlsx,
        )
        self._xlsx_btn.grid(row=0, column=4, padx=4, pady=10)

        self._json_btn = ctk.CTkButton(
            bar,
            text="{ } Exportar .json",
            font=FONT_BODY,
            width=130,
            height=36,
            fg_color="#5D4037",
            state="disabled",
            command=self._export_json,
        )
        self._json_btn.grid(row=0, column=5, padx=(4, 12), pady=10)

    # ------------------------------------------------------------------
    # callbacks de archivos
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
    # procesamiento (en hilos de fondo)
    # ------------------------------------------------------------------

    def _process_all(self) -> None:
        pending = self._state.processable_entries
        if not pending:
            self._log.warn("No hay archivos pendientes de procesar.")
            return

        self._process_btn.configure(state="disabled")
        self._log.info(f"Procesando {len(pending)} archivo(s)…")

        for entry in pending:
            entry.status = FileStatus.PROCESSING
            self._file_list.refresh()
            thread = threading.Thread(
                target=self._worker,
                args=(entry,),
                daemon=True,
            )
            thread.start()

        self.after(self._POLL_MS, self._poll_results)

    def _worker(self, entry: FileEntry) -> None:
        """Corre en hilo de fondo. No toca la GUI directamente."""
        try:
            statements = process_file(entry.path)
            self._result_queue.put(("ok", entry, statements))
        except BankParserError as exc:
            self._result_queue.put(("error", entry, str(exc)))
        except Exception as exc:
            self._result_queue.put(("error", entry, f"Error inesperado: {exc}"))

    def _poll_results(self) -> None:
        """Drena la cola de resultados desde el hilo principal."""
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

        total_movs = entry.movement_count
        banco = entry.bank_display
        rfc = entry.rfc_display
        level = "warn" if entry.has_warnings else "ok"
        self._log.log(
            f"{entry.path.name} → {banco} | RFC: {rfc} | {total_movs} movimientos",
            level,
        )
        self._file_list.refresh()

    def _handle_error(self, entry: FileEntry, msg: str) -> None:
        entry.status = FileStatus.ERROR
        entry.error = msg
        self._log.error(f"{entry.path.name}: {msg}")
        self._file_list.refresh()

    def _on_processing_done(self) -> None:
        self._process_btn.configure(state="normal")
        self._update_buttons()

        ok_count = sum(
            1 for e in self._state.entries if e.status in (FileStatus.OK, FileStatus.WARNING)
        )
        self._log.info(f"Procesamiento completo. {ok_count} archivo(s) listos para exportar.")

        # Actualizar preview si está visible
        if self._preview_visible and self._preview_frame:
            self._preview_frame.load(self._state.all_statements)

    # ------------------------------------------------------------------
    # exportación
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
    # preview
    # ------------------------------------------------------------------

    def _toggle_preview(self) -> None:
        if self._preview_visible:
            if self._preview_frame:
                self._preview_frame.grid_forget()
                self._preview_frame.destroy()
                self._preview_frame = None
            self._preview_visible = False
            self._preview_btn.configure(text="▶  Mostrar vista previa de movimientos")
            # Compactar la ventana
            self.geometry("860x780")
        else:
            self._preview_frame = PreviewTable(self)
            self._preview_frame.grid(row=3, column=0, sticky="nsew", padx=12, pady=4)
            # El log baja a fila 3+1 → necesitamos reconfigurar el grid
            self._log.grid(row=3, column=0, sticky="nsew", padx=12, pady=4)
            self._preview_frame = PreviewTable(self)
            self._preview_frame.grid(row=6, column=0, sticky="nsew", padx=12, pady=4)
            self.grid_rowconfigure(6, weight=1)
            self._preview_frame.load(self._state.all_statements)
            self._preview_visible = True
            self._preview_btn.configure(text="▼  Ocultar vista previa de movimientos")
            self.geometry("860x1100")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # auto-update
    # ------------------------------------------------------------------

    def _start_update_check(self) -> None:
        """Lanza el check de updates en un hilo de fondo."""
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
        info = self._pending_update
        answer = messagebox.askyesno(
            "Actualización disponible",
            f"{info.display_message}\n\n¿Abrir la página de descarga en el navegador?",
        )
        if answer:
            open_release_page(info)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _choose_output_dir(self) -> None:
        d = filedialog.askdirectory(
            title="Seleccionar carpeta de salida",
            initialdir=self._state.output_dir,
        )
        if d:
            self._state.output_dir = Path(d)
            self._output_label.configure(text=self._truncate_path(self._state.output_dir))

    def _update_buttons(self) -> None:
        can = self._state.can_export
        state = "normal" if can else "disabled"
        self._xlsx_btn.configure(state=state)
        self._json_btn.configure(state=state)

        has = self._state.has_files
        self._process_btn.configure(state="normal" if has else "disabled")

    @staticmethod
    def _truncate_path(p: Path, max_len: int = 38) -> str:
        s = str(p)
        if len(s) <= max_len:
            return s
        return "…" + s[-(max_len - 1) :]
