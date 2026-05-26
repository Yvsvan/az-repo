"""Pestaña de configuración global de la aplicación."""

from __future__ import annotations

from tkinter import filedialog, messagebox

import customtkinter as ctk

from bank_parser.config.settings import AppSettings
from bank_parser.gui.theme import (
    BG_ELEVATED,
    BORDER_DEFAULT,
    FONT_BODY,
    FONT_SMALL,
    FONT_SUBTITLE,
    GRAY_TEXT,
    TEAL,
    TEXT_PRIMARY,
)


class SettingsTab(ctk.CTkScrollableFrame):
    def __init__(self, master, settings: AppSettings, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._s = settings
        self._build()

    # ------------------------------------------------------------------
    # construcción
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        row = 0

        row = self._section("Analizador Bancario", row)
        self._bank_out_label = self._dir_row(
            "Carpeta de salida predeterminada",
            self._s.bank.output_dir,
            self._pick_bank_out,
            row,
        )
        row += 1

        self._fmt_var = ctk.StringVar(value=self._s.bank.export_format)
        row = self._radio_row(
            "Formato de exportación",
            [("Excel (.xlsx)", "xlsx"), ("JSON (.json)", "json")],
            self._fmt_var,
            self._on_fmt,
            row,
        )

        self._update_var = ctk.BooleanVar(value=self._s.bank.auto_update)
        row = self._check_row(
            "Verificar actualizaciones al iniciar", self._update_var, self._on_update, row
        )

        row = self._section("Descarga Masiva SAT", row)
        self._sat_out_label = self._dir_row(
            "Carpeta de salida CFDI",
            self._s.sat.output_dir,
            self._pick_sat_out,
            row,
        )
        row += 1

        self._tipo_var = ctk.StringVar(value=self._s.sat.tipo)
        row = self._radio_row(
            "Tipo de descarga predeterminado",
            [("Emitidos", "E"), ("Recibidos", "R"), ("Todos", "T")],
            self._tipo_var,
            self._on_tipo,
            row,
        )

        self._poll_var = ctk.StringVar(value=str(self._s.sat.poll_interval))
        row = self._spinbox_row("Intervalo de verificación (segundos)", self._poll_var, row)

        self._url_var = ctk.StringVar(value=self._s.sat.sat_api_url)
        row = self._url_row("URL solicitud SAT", self._url_var, row)

        self._desc_url_var = ctk.StringVar(value=self._s.sat.sat_descarga_url)
        row = self._url_row("URL descarga SAT", self._desc_url_var, row)

        # Botón guardar
        ctk.CTkButton(
            self,
            text="Guardar cambios",
            font=FONT_BODY,
            height=36,
            width=160,
            command=self._save,
        ).grid(row=row, column=0, pady=24, padx=16, sticky="w")

    # ------------------------------------------------------------------
    # widgets reutilizables
    # ------------------------------------------------------------------

    def _section(self, title: str, row: int) -> int:
        frame = ctk.CTkFrame(self, fg_color=BG_ELEVATED, corner_radius=6)
        frame.grid(row=row, column=0, sticky="ew", padx=8, pady=(10, 2))
        ctk.CTkFrame(frame, fg_color=TEAL, width=4, height=1, corner_radius=0).pack(
            side="left", fill="y"
        )
        ctk.CTkLabel(frame, text=title, font=FONT_SUBTITLE, text_color=TEXT_PRIMARY).pack(
            side="left", padx=12, pady=6
        )
        return row + 1

    def _dir_row(self, label: str, current: str, callback, row: int) -> ctk.CTkLabel:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=label, font=FONT_SMALL).grid(
            row=0, column=0, padx=(0, 10), sticky="w"
        )
        lbl = ctk.CTkLabel(
            frame,
            text=self._truncate(current),
            font=FONT_SMALL,
            text_color=GRAY_TEXT,
            anchor="w",
        )
        lbl.grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(
            frame,
            text="Cambiar",
            font=FONT_SMALL,
            width=80,
            height=28,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_ELEVATED,
            command=lambda: callback(lbl),
        ).grid(row=0, column=2, padx=(10, 0))
        return lbl

    def _radio_row(
        self,
        label: str,
        options: list[tuple[str, str]],
        var: ctk.StringVar,
        callback,
        row: int,
    ) -> int:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        ctk.CTkLabel(frame, text=label, font=FONT_SMALL).pack(side="left", padx=(0, 16))
        for text, val in options:
            ctk.CTkRadioButton(
                frame,
                text=text,
                variable=var,
                value=val,
                font=FONT_SMALL,
                command=callback,
            ).pack(side="left", padx=8)
        return row + 1

    def _check_row(self, label: str, var: ctk.BooleanVar, callback, row: int) -> int:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        ctk.CTkCheckBox(frame, text=label, variable=var, font=FONT_SMALL, command=callback).pack(
            side="left"
        )
        return row + 1

    def _entry_row(self, label: str, var: ctk.StringVar, row: int) -> int:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        ctk.CTkLabel(frame, text=label, font=FONT_SMALL).pack(side="left", padx=(0, 10))
        ctk.CTkEntry(frame, textvariable=var, font=FONT_SMALL, width=90).pack(side="left")
        return row + 1

    def _spinbox_row(
        self,
        label: str,
        var: ctk.StringVar,
        row: int,
        min_val: int = 1,
        max_val: int = 3600,
        step: int = 5,
    ) -> int:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        ctk.CTkLabel(frame, text=label, font=FONT_SMALL).pack(side="left", padx=(0, 10))

        def _dec() -> None:
            try:
                var.set(str(max(min_val, int(var.get()) - step)))
            except ValueError:
                var.set(str(min_val))

        def _inc() -> None:
            try:
                var.set(str(min(max_val, int(var.get()) + step)))
            except ValueError:
                var.set(str(min_val))

        btn_kw = dict(
            font=FONT_BODY,
            width=28,
            height=26,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_ELEVATED,
        )
        ctk.CTkButton(frame, text="-", command=_dec, **btn_kw).pack(side="left")
        ctk.CTkEntry(frame, textvariable=var, font=FONT_SMALL, width=72).pack(side="left", padx=4)
        ctk.CTkButton(frame, text="+", command=_inc, **btn_kw).pack(side="left")
        return row + 1

    # ------------------------------------------------------------------
    # callbacks
    # ------------------------------------------------------------------

    def _pick_bank_out(self, label: ctk.CTkLabel) -> None:
        d = filedialog.askdirectory(
            title="Carpeta de salida (Analizador)", initialdir=self._s.bank.output_dir
        )
        if d:
            self._s.bank.output_dir = d
            label.configure(text=self._truncate(d))

    def _pick_sat_out(self, label: ctk.CTkLabel) -> None:
        d = filedialog.askdirectory(
            title="Carpeta de salida (CFDI)", initialdir=self._s.sat.output_dir
        )
        if d:
            self._s.sat.output_dir = d
            label.configure(text=self._truncate(d))

    def _on_fmt(self) -> None:
        self._s.bank.export_format = self._fmt_var.get()  # type: ignore[assignment]

    def _on_update(self) -> None:
        self._s.bank.auto_update = self._update_var.get()

    def _on_tipo(self) -> None:
        self._s.sat.tipo = self._tipo_var.get()

    def _url_row(self, label: str, var: ctk.StringVar, row: int) -> int:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame, text=label, font=FONT_SMALL).grid(
            row=0, column=0, padx=(0, 10), sticky="w"
        )
        ctk.CTkEntry(frame, textvariable=var, font=FONT_SMALL).grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(
            frame,
            text="Probar",
            font=FONT_SMALL,
            width=72,
            height=28,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_ELEVATED,
            command=lambda: self._test_url(var.get()),
        ).grid(row=0, column=2, padx=(8, 0))
        return row + 1

    def _test_url(self, url: str) -> None:
        import threading

        from bank_parser.sat_downloader.client import SatApiClient

        def _run():
            ok, msg = SatApiClient.test_connectivity(url)
            if ok:
                messagebox.showinfo("Conexión OK", msg)
            else:
                messagebox.showerror("Sin conexión", msg)

        threading.Thread(target=_run, daemon=True).start()

    def _save(self) -> None:
        self._s.sat.sat_api_url = self._url_var.get().rstrip("/")
        self._s.sat.sat_descarga_url = self._desc_url_var.get().rstrip("/")
        try:
            self._s.sat.poll_interval = int(self._poll_var.get())
        except ValueError:
            pass
        self._s.save()
        messagebox.showinfo(
            "Configuración guardada", "Los cambios se aplicarán en la próxima sesión."
        )

    @staticmethod
    def _truncate(s: str, n: int = 50) -> str:
        return s if len(s) <= n else "…" + s[-(n - 1) :]
