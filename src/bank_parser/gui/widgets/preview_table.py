"""Widget tabla de movimientos — vista previa de los statements procesados."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from bank_parser.core.schema import Statement
from bank_parser.gui.theme import BLUE_DARK, FONT_SMALL, FONT_SUBTITLE, GRAY_TEXT

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


class PreviewTable(ctk.CTkFrame):
    """Treeview de movimientos con filtro por RFC."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._statements: list[Statement] = []
        self._build()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(4, 2))
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
        ctk.CTkLabel(header, text="RFC:", font=FONT_SMALL, text_color=GRAY_TEXT).pack(
            side="right", padx=(0, 4)
        )

        # Frame contenedor para el Treeview (ttk, no CTk)
        tree_frame = ctk.CTkFrame(self)
        tree_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "BankParser.Treeview",
            background="#2b2b2b",
            foreground="white",
            fieldbackground="#2b2b2b",
            rowheight=22,
            font=("Consolas", 10),
        )
        style.configure(
            "BankParser.Treeview.Heading",
            background=BLUE_DARK,
            foreground="white",
            font=("Segoe UI", 10, "bold"),
        )
        style.map("BankParser.Treeview", background=[("selected", "#1F4E79")])

        self._tree = ttk.Treeview(
            tree_frame,
            columns=_COLUMNS,
            show="headings",
            style="BankParser.Treeview",
            height=12,
        )

        for col in _COLUMNS:
            self._tree.heading(col, text=col.capitalize())
            self._tree.column(col, width=_COL_WIDTHS[col], minwidth=60)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self._count_label = ctk.CTkLabel(
            self, text="0 movimientos", font=FONT_SMALL, text_color=GRAY_TEXT
        )
        self._count_label.pack(anchor="e", padx=8, pady=(0, 4))

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def load(self, statements: list[Statement]) -> None:
        """Carga statements y refresca la tabla."""
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
                self._tree.insert(
                    "",
                    "end",
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
