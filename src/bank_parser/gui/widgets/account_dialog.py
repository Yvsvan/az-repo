"""Modal dialog for adding a SAT e.firma account."""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from bank_parser.gui.theme import (
    BG_ELEVATED,
    BG_SURFACE,
    BORDER_DEFAULT,
    CRIMSON,
    FONT_BODY,
    FONT_SMALL,
    FONT_SUBTITLE,
    GRAY_TEXT,
    TEAL,
    TEXT_PRIMARY,
)


class AddAccountDialog(ctk.CTkToplevel):
    """Single-modal dialog: pick .cer / .key files, enter alias + password."""

    def __init__(self, master) -> None:
        super().__init__(master)
        self.title("Agregar cuenta SAT")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self._cer: Path | None = None
        self._key: Path | None = None
        self._result: tuple[Path, Path, str, str] | None = None
        self._show_pass = False
        self._build()
        self.after(80, self._grab_focus)

    @classmethod
    def ask(cls, master) -> tuple[Path, Path, str, str] | None:
        dlg = cls(master)
        dlg.wait_window()
        return dlg._result

    def _grab_focus(self) -> None:
        self.grab_set()
        self.focus_force()

    def _build(self) -> None:
        self.configure(fg_color=BG_SURFACE)
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(padx=20, pady=16, fill="both", expand=True)
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            f,
            text="Nueva cuenta SAT",
            font=FONT_SUBTITLE,
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=0, columnspan=3, pady=(0, 12), sticky="w")

        # .cer file
        ctk.CTkLabel(f, text="Certificado (.cer):", font=FONT_SMALL).grid(
            row=1,
            column=0,
            sticky="w",
            pady=5,
        )
        self._cer_lbl = ctk.CTkLabel(
            f,
            text="Sin seleccionar",
            font=FONT_SMALL,
            text_color=GRAY_TEXT,
            anchor="w",
        )
        self._cer_lbl.grid(row=1, column=1, sticky="ew", padx=(10, 6), pady=5)
        ctk.CTkButton(
            f,
            text="Examinar",
            font=FONT_SMALL,
            width=82,
            height=28,
            command=self._pick_cer,
        ).grid(row=1, column=2, pady=5)

        # .key file
        ctk.CTkLabel(f, text="Llave (.key):", font=FONT_SMALL).grid(
            row=2,
            column=0,
            sticky="w",
            pady=5,
        )
        self._key_lbl = ctk.CTkLabel(
            f,
            text="Sin seleccionar",
            font=FONT_SMALL,
            text_color=GRAY_TEXT,
            anchor="w",
        )
        self._key_lbl.grid(row=2, column=1, sticky="ew", padx=(10, 6), pady=5)
        ctk.CTkButton(
            f,
            text="Examinar",
            font=FONT_SMALL,
            width=82,
            height=28,
            command=self._pick_key,
        ).grid(row=2, column=2, pady=5)

        # Alias
        ctk.CTkLabel(f, text="Alias (opcional):", font=FONT_SMALL).grid(
            row=3,
            column=0,
            sticky="w",
            pady=5,
        )
        self._alias_var = ctk.StringVar()
        ctk.CTkEntry(f, textvariable=self._alias_var, font=FONT_SMALL).grid(
            row=3,
            column=1,
            columnspan=2,
            sticky="ew",
            padx=(10, 0),
            pady=5,
        )

        # Password
        ctk.CTkLabel(f, text="Contraseña:", font=FONT_SMALL).grid(
            row=4,
            column=0,
            sticky="w",
            pady=5,
        )
        pass_row = ctk.CTkFrame(f, fg_color="transparent")
        pass_row.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=5)
        pass_row.grid_columnconfigure(0, weight=1)
        self._pass_var = ctk.StringVar()
        self._pass_entry = ctk.CTkEntry(
            pass_row, textvariable=self._pass_var, show="*", font=FONT_SMALL
        )
        self._pass_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            pass_row,
            text="◎",
            width=28,
            height=28,
            font=("Segoe UI", 13),
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_ELEVATED,
            command=self._toggle_pass,
        ).grid(row=0, column=1, padx=(4, 0))

        # Buttons
        btn_row = ctk.CTkFrame(f, fg_color="transparent")
        btn_row.grid(row=5, column=0, columnspan=3, pady=(18, 0), sticky="e")
        ctk.CTkButton(
            btn_row,
            text="Cancelar",
            font=FONT_SMALL,
            width=90,
            height=32,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_ELEVATED,
            command=self.destroy,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row,
            text="Agregar",
            font=FONT_BODY,
            width=90,
            height=32,
            fg_color=TEAL,
            command=self._confirm,
        ).pack(side="left")

    def _pick_cer(self) -> None:
        p = filedialog.askopenfilename(
            title="Seleccionar certificado (.cer)",
            filetypes=[("Certificado SAT", "*.cer"), ("Todos", "*.*")],
        )
        if p:
            self._cer = Path(p)
            self._cer_lbl.configure(text=self._cer.name, text_color=TEXT_PRIMARY)

    def _pick_key(self) -> None:
        p = filedialog.askopenfilename(
            title="Seleccionar llave privada (.key)",
            filetypes=[("Llave privada", "*.key"), ("Todos", "*.*")],
        )
        if p:
            self._key = Path(p)
            self._key_lbl.configure(text=self._key.name, text_color=TEXT_PRIMARY)

    def _toggle_pass(self) -> None:
        self._show_pass = not self._show_pass
        self._pass_entry.configure(show="" if self._show_pass else "*")

    def _confirm(self) -> None:
        if not self._cer:
            self._cer_lbl.configure(text="¡Requerido!", text_color=CRIMSON)
            return
        if not self._key:
            self._key_lbl.configure(text="¡Requerido!", text_color=CRIMSON)
            return
        pwd = self._pass_var.get()
        if not pwd:
            self._pass_entry.configure(border_color=CRIMSON)
            return
        self._result = (self._cer, self._key, pwd, self._alias_var.get())
        self.destroy()
