"""Convertidor XML — pestaña para convertir CFDIs descargados a Excel."""

from __future__ import annotations

import queue
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from bank_parser.gui.theme import (
    BG_ELEVATED,
    BG_SURFACE,
    BLUE_DARK,
    BORDER_DEFAULT,
    FONT_BODY,
    FONT_SMALL,
    FONT_SUBTITLE,
    GRAY_TEXT,
    GREEN_DARK,
    TEAL,
    TEXT_PRIMARY,
)
from bank_parser.gui.widgets.progress_log import ProgressLog


class _SourceList(ctk.CTkScrollableFrame):
    """Scrollable list of source paths (ZIPs or folders) with remove buttons."""

    def __init__(self, master, on_change, **kwargs) -> None:
        super().__init__(
            master,
            height=80,
            fg_color=BG_ELEVATED,
            border_width=1,
            border_color=BORDER_DEFAULT,
            **kwargs,
        )
        self._paths: list[Path] = []
        self._on_change = on_change
        self.grid_columnconfigure(0, weight=1)
        self._refresh_ui()

    @property
    def paths(self) -> list[Path]:
        return list(self._paths)

    def add_paths(self, new_paths: list[Path]) -> int:
        added = 0
        for p in new_paths:
            if p not in self._paths:
                self._paths.append(p)
                added += 1
        if added:
            self._refresh_ui()
            self._on_change()
        return added

    def clear(self) -> None:
        self._paths.clear()
        self._refresh_ui()
        self._on_change()

    def _remove(self, path: Path) -> None:
        self._paths.remove(path)
        self._refresh_ui()
        self._on_change()

    def _refresh_ui(self) -> None:
        for w in self.winfo_children():
            w.destroy()

        if not self._paths:
            ctk.CTkLabel(
                self,
                text="  (Sin archivos. Agrega ZIPs o carpetas)",
                font=FONT_SMALL,
                text_color=GRAY_TEXT,
            ).grid(row=0, column=0, pady=8, sticky="w")
            return

        for i, path in enumerate(self._paths):
            row_frame = ctk.CTkFrame(self, fg_color="transparent")
            row_frame.grid(row=i, column=0, sticky="ew", pady=1)
            row_frame.grid_columnconfigure(0, weight=1)

            icon = "📦" if path.suffix.lower() == ".zip" else "📁"
            ctk.CTkLabel(
                row_frame,
                text=f"  {icon}  {path.name}",
                font=FONT_SMALL,
                text_color=TEXT_PRIMARY,
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=4)

            ctk.CTkButton(
                row_frame,
                text="✕",
                width=22,
                height=22,
                font=FONT_SMALL,
                fg_color="transparent",
                border_width=1,
                border_color=BORDER_DEFAULT,
                hover_color=BG_SURFACE,
                command=lambda p=path: self._remove(p),
            ).grid(row=0, column=1, padx=(4, 6))


class XmlConverterTab(ctk.CTkFrame):
    """Pestaña para convertir paquetes de CFDIs (ZIPs o carpetas) a Excel.

    Two-step flow:
      1. Add sources → click "Escanear RFCs" → top RFC candidates appear inline.
      2. Pick target RFC → click "Convertir a Excel" → Excel written.
    """

    _POLL_MS = 150

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self._result_queue: queue.Queue = queue.Queue()
        self._running = False

        # Cached after scan step — reused by convert step
        self._rows: list | None = None
        self._rfc_var = ctk.StringVar(value="")

        self._build()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.grid_rowconfigure(3, weight=1)  # log stretches
        self.grid_columnconfigure(0, weight=1)

        self._build_sources()  # row 0
        self._build_rfc_picker()  # row 1 (hidden until scan)
        self._build_output()  # row 2
        self._build_log()  # row 3
        self._build_action_bar()  # row 4

    def _build_sources(self) -> None:
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        outer.grid_columnconfigure(0, weight=1)

        # Section header
        hdr = ctk.CTkFrame(outer, fg_color=BG_ELEVATED, corner_radius=6)
        hdr.grid(row=0, column=0, sticky="ew")

        ctk.CTkFrame(hdr, fg_color=TEAL, width=4, height=1, corner_radius=0).pack(
            side="left", fill="y"
        )
        ctk.CTkLabel(
            hdr, text="Archivos de entrada", font=FONT_SUBTITLE, text_color=TEXT_PRIMARY
        ).pack(side="left", padx=12, pady=6)

        ctk.CTkButton(
            hdr,
            text="Limpiar",
            font=FONT_SMALL,
            width=60,
            height=22,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_SURFACE,
            command=self._on_clear_sources,
        ).pack(side="right", padx=(0, 8))

        ctk.CTkButton(
            hdr,
            text="Carpeta",
            font=FONT_SMALL,
            width=70,
            height=22,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_SURFACE,
            command=self._add_folder,
        ).pack(side="right", padx=(0, 4))

        ctk.CTkButton(
            hdr,
            text="Agregar ZIPs",
            font=FONT_SMALL,
            width=90,
            height=22,
            fg_color=TEAL,
            hover_color="#0B7A71",
            command=self._add_zips,
        ).pack(side="right", padx=(0, 4))

        # Source list
        self._source_list = _SourceList(outer, on_change=self._on_sources_changed)
        self._source_list.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        # "Escanear RFCs" action row beneath list
        scan_row = ctk.CTkFrame(outer, fg_color="transparent")
        scan_row.grid(row=2, column=0, sticky="ew", pady=(6, 0))

        self._scan_btn = ctk.CTkButton(
            scan_row,
            text="🔍  Escanear RFCs",
            font=FONT_BODY,
            width=160,
            height=32,
            fg_color=TEAL,
            hover_color="#0B7A71",
            state="disabled",
            command=self._on_scan,
        )
        self._scan_btn.pack(side="left")

        self._scan_status_lbl = ctk.CTkLabel(
            scan_row, text="", font=FONT_SMALL, text_color=GRAY_TEXT
        )
        self._scan_status_lbl.pack(side="left", padx=10)

    def _build_rfc_picker(self) -> None:
        """RFC Objetivo section — hidden until scan completes."""
        self._rfc_picker_expanded = True
        self._rfc_candidates: list[tuple[str, str, int]] = []

        self._rfc_outer = ctk.CTkFrame(self, fg_color="transparent")
        # will be grid(row=1) when shown; hidden initially
        self._rfc_outer.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(self._rfc_outer, fg_color=BG_ELEVATED, corner_radius=6)
        hdr.grid(row=0, column=0, sticky="ew")

        ctk.CTkFrame(hdr, fg_color=TEAL, width=4, height=1, corner_radius=0).pack(
            side="left", fill="y"
        )
        ctk.CTkLabel(hdr, text="RFC Objetivo", font=FONT_SUBTITLE, text_color=TEXT_PRIMARY).pack(
            side="left", padx=12, pady=6
        )

        # Toggle arrow (right side)
        self._rfc_toggle_btn = ctk.CTkButton(
            hdr,
            text="▲",
            font=FONT_SMALL,
            width=28,
            height=22,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_SURFACE,
            command=self._toggle_rfc_picker,
        )
        self._rfc_toggle_btn.pack(side="right", padx=(0, 8))

        # Preview of selected RFC shown when collapsed
        self._rfc_preview_lbl = ctk.CTkLabel(hdr, text="", font=FONT_SMALL, text_color=GRAY_TEXT)
        self._rfc_preview_lbl.pack(side="right", padx=(0, 4))

        # Radio buttons will be inserted here dynamically
        self._rfc_radio_frame = ctk.CTkScrollableFrame(
            self._rfc_outer,
            height=100,
            fg_color=BG_ELEVATED,
            border_width=1,
            border_color=BORDER_DEFAULT,
        )
        self._rfc_radio_frame.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._rfc_radio_frame.grid_columnconfigure(0, weight=1)

    def _populate_rfc_picker(self, candidates: list[tuple[str, str, int]]) -> None:
        """Rebuild radio buttons from (rfc, nombre, count) list and show the section."""
        self._rfc_candidates = candidates

        for w in self._rfc_radio_frame.winfo_children():
            w.destroy()

        # Pre-select the top candidate
        if candidates:
            self._rfc_var.set(candidates[0][0])

        for i, (rfc, nombre, count) in enumerate(candidates):
            label_text = f"  {rfc}   {nombre}   ({count} CFDIs)"
            ctk.CTkRadioButton(
                self._rfc_radio_frame,
                text=label_text,
                variable=self._rfc_var,
                value=rfc,
                font=FONT_SMALL,
                text_color=TEXT_PRIMARY,
                fg_color=TEAL,
                border_color=BORDER_DEFAULT,
                command=self._on_rfc_selected,
            ).grid(row=i, column=0, sticky="w", padx=8, pady=2)

        # "Todos" option
        ctk.CTkRadioButton(
            self._rfc_radio_frame,
            text="  Todos (sin filtro)",
            variable=self._rfc_var,
            value="",
            font=FONT_SMALL,
            text_color=GRAY_TEXT,
            fg_color=TEAL,
            border_color=BORDER_DEFAULT,
            command=self._on_rfc_selected,
        ).grid(row=len(candidates), column=0, sticky="w", padx=8, pady=2)

        # Always expand when freshly populated
        self._rfc_picker_expanded = True
        self._rfc_toggle_btn.configure(text="▲")
        self._rfc_radio_frame.grid()

        # Show the section and update preview
        self._rfc_outer.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 2))
        self._on_rfc_selected()

    def _toggle_rfc_picker(self) -> None:
        if self._rfc_picker_expanded:
            self._rfc_radio_frame.grid_remove()
            self._rfc_toggle_btn.configure(text="▼")
            self._rfc_picker_expanded = False
        else:
            self._rfc_radio_frame.grid()
            self._rfc_toggle_btn.configure(text="▲")
            self._rfc_picker_expanded = True

    def _hide_rfc_picker(self) -> None:
        self._rfc_outer.grid_remove()
        self._rfc_var.set("")
        self._rfc_preview_lbl.configure(text="")

    def _build_output(self) -> None:
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.grid(row=2, column=0, sticky="ew", padx=8, pady=(6, 2))
        outer.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(outer, fg_color=BG_ELEVATED, corner_radius=6)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(2, weight=1)

        ctk.CTkFrame(hdr, fg_color=TEAL, width=4, height=1, corner_radius=0).grid(
            row=0, column=0, sticky="ns"
        )
        ctk.CTkLabel(hdr, text="Guardar como:", font=FONT_SUBTITLE, text_color=TEXT_PRIMARY).grid(
            row=0, column=1, padx=12, pady=8, sticky="w"
        )

        self._output_entry = ctk.CTkEntry(
            hdr, font=FONT_BODY, placeholder_text="Selecciona la carpeta de destino..."
        )
        self._output_entry.grid(row=0, column=2, sticky="ew", padx=(0, 4), pady=6)

        ctk.CTkButton(
            hdr,
            text="…",
            width=32,
            height=28,
            font=FONT_BODY,
            command=self._browse_output,
        ).grid(row=0, column=3, padx=(0, 10), pady=6)

    def _build_log(self) -> None:
        self._log = ProgressLog(self)
        self._log.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)

    def _build_action_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=BLUE_DARK, corner_radius=0)
        bar.grid(row=4, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)

        self._convert_btn = ctk.CTkButton(
            bar,
            text="▶  Convertir a Excel",
            font=FONT_SUBTITLE,
            width=180,
            height=36,
            fg_color=GREEN_DARK,
            state="disabled",
            command=self._on_convert,
        )
        self._convert_btn.grid(row=0, column=1, padx=14, pady=10)

        self._summary_lbl = ctk.CTkLabel(bar, text="", font=FONT_SMALL, text_color=GRAY_TEXT)
        self._summary_lbl.grid(row=0, column=0, padx=14, pady=10, sticky="w")

        self._progress_bar = ctk.CTkProgressBar(
            bar, mode="indeterminate", height=4, progress_color=TEAL
        )
        self._progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._progress_bar.grid_remove()

    # ------------------------------------------------------------------
    # Source management callbacks
    # ------------------------------------------------------------------

    def _on_sources_changed(self) -> None:
        has = bool(self._source_list.paths)
        self._scan_btn.configure(state="normal" if has else "disabled")

        # Invalidate previous scan result
        self._rows = None
        self._hide_rfc_picker()
        self._convert_btn.configure(state="disabled")
        self._scan_status_lbl.configure(text="")
        self._summary_lbl.configure(text="")

        # Auto-fill output path from first source
        if has and not self._output_entry.get().strip():
            first = self._source_list.paths[0]
            folder = first.parent if first.is_file() else first
            date_str = datetime.now().strftime("%Y-%m-%d")
            self._output_entry.delete(0, "end")
            self._output_entry.insert(0, str(folder / f"cfdi_{date_str}.xlsx"))

    def _on_clear_sources(self) -> None:
        self._source_list.clear()

    def _add_zips(self) -> None:
        files = filedialog.askopenfilenames(
            title="Seleccionar paquetes ZIP del SAT",
            filetypes=[("ZIP", "*.zip"), ("Todos", "*.*")],
        )
        if files:
            added = self._source_list.add_paths([Path(f) for f in files])
            if added:
                self._log.info(f"{added} archivo(s) agregado(s).")

    def _add_folder(self) -> None:
        d = filedialog.askdirectory(title="Seleccionar carpeta con XMLs")
        if d:
            added = self._source_list.add_paths([Path(d)])
            if added:
                self._log.info(f"Carpeta agregada: {Path(d).name}")

    def _browse_output(self) -> None:
        current = self._output_entry.get().strip()
        initial_dir = Path(current).parent if current else Path.home()
        dest = filedialog.asksaveasfilename(
            title="Guardar Excel como",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialdir=initial_dir,
            initialfile=Path(current).name if current else "cfdi.xlsx",
        )
        if dest:
            self._output_entry.delete(0, "end")
            self._output_entry.insert(0, dest)

    def _on_rfc_selected(self) -> None:
        self._convert_btn.configure(state="normal")
        rfc = self._rfc_var.get()
        if rfc:
            nombre = next((n for r, n, _ in self._rfc_candidates if r == rfc), "")
            preview = f"{rfc}  —  {nombre}" if nombre else rfc
        else:
            preview = "Todos (sin filtro)"
        self._rfc_preview_lbl.configure(text=preview)

    # ------------------------------------------------------------------
    # Step 1: Scan
    # ------------------------------------------------------------------

    def _on_scan(self) -> None:
        sources = self._source_list.paths
        if not sources:
            return

        self._scan_btn.configure(state="disabled")
        self._hide_rfc_picker()
        self._convert_btn.configure(state="disabled")
        self._summary_lbl.configure(text="")
        self._progress_bar.grid()
        self._progress_bar.start()
        self._running = True
        self._log.clear()
        self._log.info("Escaneando XMLs…")

        threading.Thread(target=self._scan_worker, args=(sources,), daemon=True).start()
        self.after(self._POLL_MS, self._poll)

    def _scan_worker(self, sources: list[Path]) -> None:
        try:
            from bank_parser.cfdi_converter.loader import load_sources
            from bank_parser.cfdi_converter.rfc_detector import detect_rfcs

            def cb(msg: str, level: str = "info") -> None:
                self._result_queue.put(("log", msg, level))

            rows = load_sources(sources, progress_cb=cb)
            candidates = detect_rfcs(rows, top_n=5)
            self._result_queue.put(("scan_done", rows, candidates))
        except Exception as exc:
            self._result_queue.put(("error", f"Error al escanear: {exc}"))

    # ------------------------------------------------------------------
    # Step 2: Convert
    # ------------------------------------------------------------------

    def _on_convert(self) -> None:
        if self._rows is None:
            return

        output_path = self._output_entry.get().strip()
        if not output_path:
            messagebox.showwarning("Falta ruta de salida", "Indica dónde guardar el Excel.")
            return

        target_rfc = self._rfc_var.get() or None

        self._convert_btn.configure(state="disabled")
        self._scan_btn.configure(state="disabled")
        self._summary_lbl.configure(text="")
        self._progress_bar.grid()
        self._progress_bar.start()
        self._running = True
        self._log.info("Exportando a Excel…")

        threading.Thread(
            target=self._convert_worker,
            args=(self._rows, output_path, target_rfc),
            daemon=True,
        ).start()
        self.after(self._POLL_MS, self._poll)

    def _convert_worker(self, rows: list, output_path: str, target_rfc: str | None) -> None:
        try:
            from bank_parser.cfdi_converter.exporter import export_to_xlsx
            from bank_parser.cfdi_converter.schema import CfdiRow, NominaRow, PagoDocRow

            if target_rfc:
                exported_count = sum(
                    1
                    for r in rows
                    if (
                        isinstance(r, CfdiRow)
                        and (r.rfc_emisor == target_rfc or r.rfc_receptor == target_rfc)
                    )
                    or (
                        isinstance(r, NominaRow)
                        and (r.rfc_emisor == target_rfc or r.rfc_empleado == target_rfc)
                    )
                    or (isinstance(r, PagoDocRow) and r.rfc_emisor == target_rfc)
                )
            else:
                exported_count = len(rows)

            self._result_queue.put(("log", f"Exportando {exported_count} registros…", "info"))
            out = export_to_xlsx(rows, output_path, target_rfc=target_rfc)
            self._result_queue.put(("convert_done", str(out), exported_count))
        except Exception as exc:
            self._result_queue.put(("error", f"Error inesperado: {exc}"))

    # ------------------------------------------------------------------
    # Queue polling (shared by both workers)
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        try:
            while True:
                item = self._result_queue.get_nowait()
                kind = item[0]

                if kind == "log":
                    self._log.log(item[1], item[2] if len(item) > 2 else "info")

                elif kind == "scan_done":
                    rows, candidates = item[1], item[2]
                    self._on_scan_done(rows, candidates)
                    return

                elif kind == "convert_done":
                    self._on_convert_done(item[1], item[2])
                    return

                elif kind == "error":
                    self._on_error(item[1])
                    return

        except queue.Empty:
            pass

        if self._running:
            self.after(self._POLL_MS, self._poll)

    # ------------------------------------------------------------------
    # Completion handlers
    # ------------------------------------------------------------------

    def _on_scan_done(self, rows: list, candidates: list[tuple[str, str, int]]) -> None:
        self._running = False
        self._progress_bar.stop()
        self._progress_bar.grid_remove()
        self._scan_btn.configure(state="normal")

        self._rows = rows
        total = len(rows)
        self._scan_status_lbl.configure(text=f"{total} CFDIs encontrados")
        self._log.ok(
            f"Escaneo completo: {total} CFDIs en {len(self._source_list.paths)} fuente(s)."
        )

        if candidates:
            self._populate_rfc_picker(candidates)
        else:
            self._log.warn("No se detectaron RFCs. Verifica los archivos.")

    def _on_convert_done(self, output_path: str, count: int) -> None:
        self._running = False
        self._progress_bar.stop()
        self._progress_bar.grid_remove()
        self._convert_btn.configure(state="normal")
        self._scan_btn.configure(state="normal")
        self._log.ok(f"Excel generado → {output_path}")
        self._summary_lbl.configure(text=f"{count} CFDIs exportados")
        messagebox.showinfo(
            "Conversión exitosa",
            f"{count} registros exportados a:\n{output_path}",
        )

    def _on_error(self, message: str) -> None:
        self._running = False
        self._progress_bar.stop()
        self._progress_bar.grid_remove()
        self._scan_btn.configure(state="normal" if self._source_list.paths else "disabled")
        self._convert_btn.configure(state="normal" if self._rows is not None else "disabled")
        self._log.error(message)
        messagebox.showerror("Error", message)
