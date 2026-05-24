"""Widget tabla de movimientos — vista previa de los statements procesados."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from bank_parser.core.schema import Statement
from bank_parser.gui.theme import FONT_SMALL, FONT_SUBTITLE, TEXT_SECONDARY

_COLUMNS = ("fecha", "descripcion", "abono", "cargo", "saldo", "banco", "cuenta")
_COL_WIDTHS = {
    "fecha": 90,
    "descripcion": 260,
    "abono": 100,
    "cargo": 100,
    "saldo": 110,
    "banco": 90,
    "cuenta": 110,
}

_COL_LABELS = {
    "fecha": "Fecha",
    "descripcion": "Descripción",
    "abono": "Abono",
    "cargo": "Cargo",
    "saldo": "Saldo",
    "banco": "Banco",
    "cuenta": "Cuenta",
}

# Palette (flat values — TTK doesn't use CTk tokens)
_BG_SURFACE = "#1E293B"
_BG_ELEVATED = "#263044"
_BG_INPUT = "#1A2535"
_BG_ODD = "#1C2A3B"
_TEAL = "#0D9488"
_BORDER = "#334155"
_TEXT = "#F1F5F9"
_TEXT_MUTED = "#64748B"


class PreviewTable(ctk.CTkFrame):
    """Treeview de movimientos con filtro por RFC."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._statements: list[Statement] = []
        self._build()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(8, 4))
        ctk.CTkLabel(header, text="Vista previa de movimientos", font=FONT_SUBTITLE).pack(
            side="left"
        )

        self._rfc_var = tk.StringVar(value="Todos")
        self._rfc_menu = ctk.CTkOptionMenu(
            header,
            variable=self._rfc_var,
            values=["Todos"],
            font=FONT_SMALL,
            width=160,
            command=self._on_rfc_filter,
        )
        self._rfc_menu.pack(side="right")
        ctk.CTkLabel(header, text="RFC:", font=FONT_SMALL, text_color=TEXT_SECONDARY).pack(
            side="right", padx=(0, 6)
        )

        tree_frame = ctk.CTkFrame(
            self, fg_color=_BG_SURFACE, corner_radius=8, border_width=1, border_color=_BORDER
        )
        tree_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        style = ttk.Style()
        style.theme_use("default")

        style.configure(
            "BankParser.Treeview",
            background=_BG_SURFACE,
            foreground=_TEXT,
            fieldbackground=_BG_SURFACE,
            rowheight=24,
            font=("Segoe UI", 11),
            borderwidth=0,
            relief="flat",
        )
        style.configure(
            "BankParser.Treeview.Heading",
            background=_BG_ELEVATED,
            foreground=_TEXT,
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            borderwidth=0,
        )
        style.map(
            "BankParser.Treeview",
            background=[("selected", _TEAL)],
            foreground=[("selected", _TEXT)],
        )
        style.map(
            "BankParser.Treeview.Heading",
            background=[("active", _BG_ELEVATED)],
        )

        # Scrollbar styling
        style.configure(
            "Vertical.TScrollbar",
            background=_BG_ELEVATED,
            troughcolor=_BG_SURFACE,
            arrowcolor=_TEXT_MUTED,
            bordercolor=_BORDER,
            relief="flat",
        )
        style.configure(
            "Horizontal.TScrollbar",
            background=_BG_ELEVATED,
            troughcolor=_BG_SURFACE,
            arrowcolor=_TEXT_MUTED,
            bordercolor=_BORDER,
            relief="flat",
        )

        self._tree = ttk.Treeview(
            tree_frame,
            columns=_COLUMNS,
            show="headings",
            style="BankParser.Treeview",
            height=12,
        )

        for col in _COLUMNS:
            self._tree.heading(col, text=_COL_LABELS[col])
            self._tree.column(col, width=_COL_WIDTHS[col], minwidth=60)

        self._tree.tag_configure("even", background=_BG_SURFACE)
        self._tree.tag_configure("odd", background=_BG_ODD)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self._count_label = ctk.CTkLabel(
            self, text="0 movimientos", font=FONT_SMALL, text_color=TEXT_SECONDARY
        )
        self._count_label.pack(anchor="e", padx=8, pady=(0, 4))

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def load(self, statements: list[Statement]) -> None:
        self._statements = statements
        self._update_rfc_filter()
        self._render(statements)

    def clear(self) -> None:
        self._statements = []
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._count_label.configure(text="0 movimientos")

    # ------------------------------------------------------------------
    # helpers privados
    # ------------------------------------------------------------------

    def _update_rfc_filter(self) -> None:
        rfcs = sorted({s.summary.rfc or "(sin RFC)" for s in self._statements})
        values = ["Todos", *rfcs]
        self._rfc_menu.configure(values=values)
        self._rfc_var.set("Todos")

    def _on_rfc_filter(self, value: str) -> None:
        if value == "Todos":
            self._render(self._statements)
        else:
            filtered = [s for s in self._statements if (s.summary.rfc or "(sin RFC)") == value]
            self._render(filtered)

    def _render(self, statements: list[Statement]) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)

        count = 0
        for stmt in statements:
            for mov in stmt.movements:
                tag = "even" if count % 2 == 0 else "odd"
                self._tree.insert(
                    "",
                    "end",
                    tags=(tag,),
                    values=(
                        str(mov.fecha),
                        mov.descripcion[:80],
                        f"{float(mov.abono):,.2f}" if mov.abono else "",
                        f"{float(mov.cargo):,.2f}" if mov.cargo else "",
                        f"{float(mov.saldo):,.2f}",
                        mov.banco.display_name,
                        mov.cuenta,
                    ),
                )
                count += 1

        self._count_label.configure(text=f"{count} movimientos")
