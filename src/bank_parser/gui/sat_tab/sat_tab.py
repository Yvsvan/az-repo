"""Pestaña de Descarga Masiva SAT."""

from __future__ import annotations

import os
import queue
import threading
from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from bank_parser.config.settings import AppSettings, CredentialRef
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
    RED_DARK,
    TEAL,
    TEXT_PRIMARY,
)
from bank_parser.gui.widgets.date_picker import DateEntry
from bank_parser.gui.widgets.progress_log import ProgressLog
from bank_parser.sat_downloader.schema import SatCredential, TipoDescarga


class _AccountList(ctk.CTkScrollableFrame):
    """Clickable list of loaded SAT credentials."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(
            master,
            height=70,
            fg_color=BG_ELEVATED,
            border_width=1,
            border_color=BORDER_DEFAULT,
            **kwargs,
        )
        self._selected: int | None = None
        self._btns: list[ctk.CTkButton] = []
        self.grid_columnconfigure(0, weight=1)

    @property
    def selected_index(self) -> int | None:
        return self._selected

    def refresh(self, credentials: list[SatCredential]) -> None:
        for w in self.winfo_children():
            w.destroy()
        self._btns.clear()
        self._selected = None

        if not credentials:
            ctk.CTkLabel(
                self,
                text="  (Sin cuentas cargadas)",
                font=FONT_SMALL,
                text_color=GRAY_TEXT,
            ).grid(row=0, column=0, pady=8, sticky="w")
            return

        for i, c in enumerate(credentials):
            btn = ctk.CTkButton(
                self,
                text=f"  {i + 1}.  {c.display_name}",
                font=FONT_SMALL,
                anchor="w",
                height=26,
                fg_color="transparent",
                text_color=TEXT_PRIMARY,
                hover_color=BG_ELEVATED,
                command=lambda idx=i: self._on_click(idx),
            )
            btn.grid(row=i, column=0, sticky="ew", pady=1)
            self._btns.append(btn)

    def _on_click(self, idx: int) -> None:
        if self._selected is not None and self._selected < len(self._btns):
            self._btns[self._selected].configure(fg_color="transparent", text_color=TEXT_PRIMARY)
        self._selected = idx
        self._btns[idx].configure(fg_color=TEAL, text_color="white")


class SatTab(ctk.CTkFrame):
    _POLL_MS = 200

    def __init__(self, master, settings: AppSettings, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._s = settings
        self._credentials: list[SatCredential] = []
        self._result_queue: queue.Queue = queue.Queue()
        self._cancel_event = threading.Event()
        self._running = False
        self._build()
        self._reload_saved_credentials()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_accounts()
        self._build_params()
        self._build_log()
        self._build_action_bar()

    def _build_accounts(self) -> None:
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        outer.grid_columnconfigure(0, weight=1)

        # Section header
        hdr = ctk.CTkFrame(outer, fg_color=BG_ELEVATED, corner_radius=6)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        ctk.CTkFrame(hdr, fg_color=TEAL, width=4, height=1, corner_radius=0).pack(
            side="left", fill="y"
        )
        ctk.CTkLabel(
            hdr,
            text="Cuentas (e.firma / FIEL)",
            font=FONT_SUBTITLE,
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=12, pady=6)

        # Interactive account list
        self._account_list = _AccountList(outer)
        self._account_list.grid(row=1, column=0, sticky="ew", padx=0, pady=(4, 0))

        # Buttons (right column)
        btn_col = ctk.CTkFrame(outer, fg_color="transparent")
        btn_col.grid(row=1, column=1, padx=(6, 0), pady=(4, 0), sticky="ns")

        def _btn(text, cmd, **kw):
            ctk.CTkButton(
                btn_col, text=text, font=FONT_SMALL, height=26, width=140, command=cmd, **kw
            ).pack(pady=1, fill="x")

        _btn("+ Agregar cuenta", self._add_account)
        _btn("Importar XLSX", self._import_xlsx, fg_color=GREEN_DARK)
        _btn(
            "Descargar plantilla",
            self._download_template,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_ELEVATED,
        )
        _btn("Eliminar cuenta", self._remove_account, fg_color=RED_DARK)

    def _build_params(self) -> None:
        outer = ctk.CTkFrame(self, fg_color=BG_SURFACE)
        outer.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        # Date fields
        dates = ctk.CTkFrame(outer, fg_color="transparent")
        dates.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(dates, text="Desde:", font=FONT_SMALL).pack(side="left")
        self._fecha_ini = DateEntry(dates)
        self._fecha_ini.pack(side="left", padx=(4, 20))

        ctk.CTkLabel(dates, text="Hasta:", font=FONT_SMALL).pack(side="left")
        self._fecha_fin = DateEntry(dates)
        self._fecha_fin.pack(side="left", padx=4)

        # Quick date shortcuts
        today = date.today()
        first_this = today.replace(day=1)
        last_month_end = first_this - timedelta(days=1)
        first_last = last_month_end.replace(day=1)
        m3 = today.month - 3
        y3 = today.year if today.month > 3 else today.year - 1
        m3 = m3 if m3 > 0 else m3 + 12
        first_3m = date(y3, m3, 1)
        first_year = today.replace(month=1, day=1)

        shorts = ctk.CTkFrame(outer, fg_color="transparent")
        shorts.pack(fill="x", padx=12, pady=(0, 4))
        for text, start, end in [
            ("Este mes", first_this, today),
            ("Mes anterior", first_last, last_month_end),
            ("Últimos 3 meses", first_3m, today),
            ("Este año", first_year, today),
        ]:
            ctk.CTkButton(
                shorts,
                text=text,
                font=FONT_SMALL,
                height=24,
                fg_color="transparent",
                border_width=1,
                border_color=BORDER_DEFAULT,
                hover_color=BG_ELEVATED,
                command=lambda s=start, e=end: (
                    self._fecha_ini.set_date(s),
                    self._fecha_fin.set_date(e),
                ),
            ).pack(side="left", padx=(0, 4))

        # Type + folder
        opts = ctk.CTkFrame(outer, fg_color="transparent")
        opts.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(opts, text="Tipo:", font=FONT_SMALL).pack(side="left")
        self._tipo_var = ctk.StringVar(value=self._s.sat.tipo)
        for label, val in [("Emitidos", "E"), ("Recibidos", "R"), ("Todos", "T")]:
            ctk.CTkRadioButton(
                opts, text=label, variable=self._tipo_var, value=val, font=FONT_SMALL
            ).pack(side="left", padx=8)

        ctk.CTkLabel(opts, text="   Carpeta:", font=FONT_SMALL).pack(side="left")
        self._folder_lbl = ctk.CTkLabel(
            opts,
            text=self._trunc(self._s.sat.output_dir),
            font=FONT_SMALL,
            text_color=GRAY_TEXT,
            cursor="hand2",
        )
        self._folder_lbl.pack(side="left", padx=4)
        self._folder_lbl.bind("<Button-1>", lambda _: self._open_folder())
        ctk.CTkButton(
            opts,
            text="…",
            width=32,
            height=28,
            font=FONT_BODY,
            command=self._pick_folder,
        ).pack(side="left")

    def _build_log(self) -> None:
        self._log = ProgressLog(self)
        self._log.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)

    def _build_action_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=BLUE_DARK, corner_radius=0)
        bar.grid(row=3, column=0, sticky="ew")

        self._start_btn = ctk.CTkButton(
            bar,
            text="▶  Iniciar descarga",
            font=FONT_SUBTITLE,
            width=170,
            height=36,
            command=self._start,
        )
        self._start_btn.pack(side="left", padx=12, pady=8)

        self._cancel_btn = ctk.CTkButton(
            bar,
            text="Cancelar",
            font=FONT_BODY,
            width=100,
            height=36,
            fg_color=RED_DARK,
            state="disabled",
            command=self._cancel,
        )
        self._cancel_btn.pack(side="left", padx=4, pady=8)

        self._sat_progress = ctk.CTkProgressBar(
            bar,
            mode="indeterminate",
            width=150,
            height=6,
            progress_color=TEAL,
        )
        # Not packed yet — shown during download

        self._status_lbl = ctk.CTkLabel(bar, text="", font=FONT_SMALL, text_color=GRAY_TEXT)
        self._status_lbl.pack(side="left", padx=12)

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    def _add_account(self) -> None:
        from bank_parser.gui.widgets.account_dialog import AddAccountDialog

        result = AddAccountDialog.ask(self)
        if result is None:
            return
        cer, key, password, alias = result
        self._do_add(cer, key, password, alias)

    def _do_add(self, cer: Path, key: Path, password: str, alias: str) -> None:
        from bank_parser.sat_downloader.auth import load_credential, save_password

        try:
            cred = load_credential(cer, key, password, alias)
        except Exception as exc:
            messagebox.showerror("Error al cargar credencial", str(exc))
            self._log.error(f"Error cargando {cer.name}: {exc}")
            return

        if any(c.rfc == cred.rfc for c in self._credentials):
            messagebox.showwarning("Cuenta duplicada", f"Ya existe una cuenta para RFC {cred.rfc}.")
            return

        save_password(cred.rfc, password)
        self._credentials.append(cred)
        self._persist(cred)
        self._refresh_list()
        self._log.ok(f"Cuenta agregada: {cred.display_name}")

    def _remove_account(self) -> None:
        if not self._credentials:
            return
        idx = self._account_list.selected_index
        if idx is None:
            messagebox.showinfo(
                "Seleccionar cuenta",
                "Haz clic en una cuenta de la lista para seleccionarla primero.",
            )
            return
        cred = self._credentials[idx]
        if not messagebox.askyesno(
            "Confirmar",
            f"¿Eliminar la cuenta {cred.rfc}?\nSe borrará la contraseña guardada.",
        ):
            return
        from bank_parser.sat_downloader.auth import delete_password

        delete_password(cred.rfc)
        self._credentials.pop(idx)
        self._s.sat.credentials = [c for c in self._s.sat.credentials if c.rfc != cred.rfc]
        self._s.save()
        self._refresh_list()
        self._log.info(f"Cuenta eliminada: {cred.rfc}")

    def _import_xlsx(self) -> None:
        path = filedialog.askopenfilename(
            title="Importar cuentas desde XLSX",
            filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")],
        )
        if not path:
            return
        from bank_parser.sat_downloader.account_importer import import_from_xlsx

        creds, errors = import_from_xlsx(Path(path))
        for err in errors:
            self._log.warn(err)

        added = 0
        for cred in creds:
            if any(c.rfc == cred.rfc for c in self._credentials):
                self._log.warn(f"RFC ya cargado, omitido: {cred.rfc}")
                continue
            self._credentials.append(cred)
            self._persist(cred)
            added += 1

        self._refresh_list()
        self._log.ok(f"Importación: {added} cuenta(s) cargada(s), {len(errors)} error(es)")

    def _download_template(self) -> None:
        dest = filedialog.asksaveasfilename(
            title="Guardar plantilla",
            defaultextension=".xlsx",
            initialfile="plantilla_cuentas_sat.xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not dest:
            return
        from bank_parser.sat_downloader.account_importer import generate_template

        try:
            generate_template(Path(dest))
            self._log.ok(f"Plantilla guardada → {dest}")
        except Exception as exc:
            self._log.error(f"Error guardando plantilla: {exc}")

    def _persist(self, cred: SatCredential) -> None:
        ref = CredentialRef(
            rfc=cred.rfc,
            alias=cred.alias,
            cer_path=str(cred.cer_path),
            key_path=str(cred.key_path),
        )
        self._s.sat.credentials = [c for c in self._s.sat.credentials if c.rfc != cred.rfc] + [ref]
        self._s.save()

    def _reload_saved_credentials(self) -> None:
        from bank_parser.sat_downloader.auth import load_credential, load_password

        for ref in self._s.sat.credentials:
            pwd = load_password(ref.rfc)
            if not pwd:
                self._log.warn(
                    f"Sin contraseña en Credential Manager para {ref.rfc} — agrégala manualmente"
                )
                continue
            try:
                cred = load_credential(Path(ref.cer_path), Path(ref.key_path), pwd, ref.alias)
                self._credentials.append(cred)
                self._log.ok(f"Cuenta cargada: {cred.display_name}")
            except Exception as exc:
                self._log.warn(f"No se pudo recargar {ref.rfc}: {exc}")

        self._refresh_list()

    def _refresh_list(self) -> None:
        self._account_list.refresh(self._credentials)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _pick_folder(self) -> None:
        d = filedialog.askdirectory(
            title="Carpeta de descarga CFDI", initialdir=self._s.sat.output_dir
        )
        if d:
            self._s.sat.output_dir = d
            self._folder_lbl.configure(text=self._trunc(d))

    def _open_folder(self) -> None:
        try:
            os.startfile(self._s.sat.output_dir)
        except Exception:
            pass

    def _start(self) -> None:
        if self._running:
            return
        if not self._credentials:
            messagebox.showwarning("Sin cuentas", "Agrega al menos una cuenta antes de descargar.")
            return

        fecha_ini = self._fecha_ini.get_date()
        fecha_fin = self._fecha_fin.get_date()
        if not fecha_ini or not fecha_fin:
            messagebox.showerror(
                "Fechas inválidas", "Selecciona la fecha de inicio y fin con el calendario."
            )
            return
        if fecha_ini > fecha_fin:
            messagebox.showerror(
                "Fechas inválidas", "La fecha inicial debe ser anterior a la final."
            )
            return

        tipo = TipoDescarga(self._tipo_var.get())
        output = Path(self._s.sat.output_dir)
        poll = self._s.sat.poll_interval

        self._cancel_event.clear()
        self._running = True
        self._start_btn.configure(state="disabled")
        self._cancel_btn.configure(state="normal")
        self._status_lbl.configure(text="Descargando…")
        self._sat_progress.pack(side="left", padx=8)
        self._sat_progress.start()

        self._log.info(
            f"Iniciando descarga para {len(self._credentials)} cuenta(s) | "
            f"{fecha_ini.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')} | "
            f"Tipo: {tipo.display}"
        )

        threading.Thread(
            target=self._worker,
            args=(list(self._credentials), fecha_ini, fecha_fin, tipo, output, poll),
            daemon=True,
        ).start()
        self.after(self._POLL_MS, self._poll)

    def _worker(self, creds, fecha_ini, fecha_fin, tipo, output, poll) -> None:
        from bank_parser.sat_downloader.orchestrator import run_download_session

        try:
            results = run_download_session(
                credentials=creds,
                fecha_ini=fecha_ini,
                fecha_fin=fecha_fin,
                tipo=tipo,
                output_folder=output,
                poll_interval=poll,
                progress=lambda lvl, msg: self._result_queue.put(("log", lvl, msg)),
                cancel=self._cancel_event,
            )
            self._result_queue.put(("done", results))
        except Exception as exc:
            self._result_queue.put(("error", str(exc)))

    def _poll(self) -> None:
        try:
            while True:
                item = self._result_queue.get_nowait()
                if item[0] == "log":
                    self._log.log(item[2], item[1])
                elif item[0] == "done":
                    self._finish(item[1])
                    return
                elif item[0] == "error":
                    self._log.error(f"Error inesperado: {item[1]}")
                    self._finish([])
                    return
        except queue.Empty:
            pass
        self.after(self._POLL_MS, self._poll)

    def _finish(self, results) -> None:
        self._running = False
        self._start_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")
        self._status_lbl.configure(text="")
        self._sat_progress.stop()
        self._sat_progress.pack_forget()

        total_dl = sum(r.total_downloaded for r in results)
        total_dup = sum(r.total_skipped_dup for r in results)
        total_err = sum(r.total_errors for r in results)

        summary = f"Descarga finalizada — {total_dl} XML(s) nuevos"
        if total_dup:
            summary += f", {total_dup} duplicados omitidos"
        if total_err:
            summary += f", {total_err} error(es)"
        self._log.ok(summary)

    def _cancel(self) -> None:
        self._cancel_event.set()
        self._log.warn("Cancelando… se completará la operación en curso")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _trunc(s: str, n: int = 42) -> str:
        return s if len(s) <= n else "…" + s[-(n - 1) :]
