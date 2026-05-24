"""DateEntry widget + DatePickerDialog calendar popup."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import customtkinter as ctk

from bank_parser.gui.theme import (
    BG_ELEVATED,
    BG_INPUT,
    BG_SURFACE,
    BORDER_DEFAULT,
    FONT_BODY,
    FONT_SMALL,
    FONT_SUBTITLE,
    TEAL,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

_MONTH_NAMES = [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]
_DAY_HEADERS = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"]


class DatePickerDialog(ctk.CTkToplevel):
    """Calendar dialog. Call via `DatePickerDialog.ask(master, initial)`."""

    def __init__(self, master, initial: date | None = None) -> None:
        super().__init__(master)
        self.title("Seleccionar fecha")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self._result: date | None = None
        self._viewing = (initial or date.today()).replace(day=1)
        self._selected = initial
        self._build()
        self.after(80, self._grab_focus)

    @classmethod
    def ask(cls, master, initial: date | None = None) -> date | None:
        dlg = cls(master, initial)
        dlg.wait_window()
        return dlg._result

    def _grab_focus(self) -> None:
        self.grab_set()
        self.focus_force()

    def _build(self) -> None:
        self.configure(fg_color=BG_SURFACE)
        self._inner = ctk.CTkFrame(self, fg_color="transparent")
        self._inner.pack(padx=16, pady=12, fill="both", expand=True)
        self._draw()

    def _draw(self) -> None:
        for w in self._inner.winfo_children():
            w.destroy()

        # Month / year navigation
        nav = ctk.CTkFrame(self._inner, fg_color="transparent")
        nav.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            nav,
            text="<",
            width=28,
            height=28,
            font=FONT_BODY,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_ELEVATED,
            command=self._prev_month,
        ).pack(side="left")

        ctk.CTkLabel(
            nav,
            text=f"{_MONTH_NAMES[self._viewing.month - 1]} {self._viewing.year}",
            font=FONT_SUBTITLE,
            text_color=TEXT_PRIMARY,
        ).pack(side="left", expand=True)

        ctk.CTkButton(
            nav,
            text=">",
            width=28,
            height=28,
            font=FONT_BODY,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_ELEVATED,
            command=self._next_month,
        ).pack(side="right")

        # Day-of-week headers
        hdr = ctk.CTkFrame(self._inner, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 2))
        for i, d in enumerate(_DAY_HEADERS):
            ctk.CTkLabel(
                hdr,
                text=d,
                font=FONT_SMALL,
                text_color=TEXT_MUTED,
                width=36,
            ).grid(row=0, column=i, padx=1)

        # Calendar day grid
        grid_frame = ctk.CTkFrame(self._inner, fg_color="transparent")
        grid_frame.pack(fill="x")
        weeks = calendar.monthcalendar(self._viewing.year, self._viewing.month)
        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                if day == 0:
                    ctk.CTkFrame(
                        grid_frame,
                        width=36,
                        height=30,
                        fg_color="transparent",
                    ).grid(row=r, column=c, padx=1, pady=1)
                else:
                    d = date(self._viewing.year, self._viewing.month, day)
                    is_sel = d == self._selected
                    ctk.CTkButton(
                        grid_frame,
                        text=str(day),
                        width=36,
                        height=30,
                        font=FONT_SMALL,
                        fg_color=TEAL if is_sel else "transparent",
                        text_color=TEXT_PRIMARY if is_sel else TEXT_SECONDARY,
                        hover_color=BG_ELEVATED,
                        corner_radius=4,
                        command=lambda _d=d: self._select(_d),
                    ).grid(row=r, column=c, padx=1, pady=1)

        # Quick-select shortcuts
        today = date.today()
        first_this = today.replace(day=1)
        last_month_end = first_this - timedelta(days=1)
        first_last = last_month_end.replace(day=1)
        shortcuts = [
            ("Este mes", first_this),
            ("Mes anterior", first_last),
            ("Hoy", today),
        ]
        short_row = ctk.CTkFrame(self._inner, fg_color="transparent")
        short_row.pack(fill="x", pady=(10, 0))
        for text, d in shortcuts:
            ctk.CTkButton(
                short_row,
                text=text,
                font=FONT_SMALL,
                height=26,
                fg_color="transparent",
                border_width=1,
                border_color=BORDER_DEFAULT,
                hover_color=BG_ELEVATED,
                command=lambda _d=d: self._select(_d),
            ).pack(side="left", padx=(0, 4))

    def _select(self, d: date) -> None:
        self._result = d
        self.destroy()

    def _prev_month(self) -> None:
        y, m = self._viewing.year, self._viewing.month
        self._viewing = date(y - 1 if m == 1 else y, 12 if m == 1 else m - 1, 1)
        self._draw()

    def _next_month(self) -> None:
        y, m = self._viewing.year, self._viewing.month
        self._viewing = date(y + 1 if m == 12 else y, 1 if m == 12 else m + 1, 1)
        self._draw()


class DateEntry(ctk.CTkFrame):
    """Compact date field with calendar-popup button."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._date: date | None = None
        self._build()

    def _build(self) -> None:
        display = ctk.CTkFrame(
            self,
            fg_color=BG_INPUT,
            corner_radius=6,
            border_width=1,
            border_color=BORDER_DEFAULT,
        )
        display.pack(side="left")
        self._lbl = ctk.CTkLabel(
            display,
            text="dd/mm/aaaa",
            font=FONT_SMALL,
            text_color=TEXT_MUTED,
            width=100,
            anchor="w",
        )
        self._lbl.pack(padx=8, pady=4)
        display.bind("<Button-1>", lambda _: self._pick())
        self._lbl.bind("<Button-1>", lambda _: self._pick())
        display.configure(cursor="hand2")
        self._lbl.configure(cursor="hand2")

        ctk.CTkButton(
            self,
            text="⊞",
            width=28,
            height=28,
            font=("Segoe UI", 13),
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_DEFAULT,
            hover_color=BG_ELEVATED,
            command=self._pick,
        ).pack(side="left", padx=(4, 0))

    def _pick(self) -> None:
        result = DatePickerDialog.ask(self, initial=self._date)
        if result is not None:
            self._date = result
            self._lbl.configure(
                text=result.strftime("%d/%m/%Y"),
                text_color=TEXT_PRIMARY,
            )

    def get_date(self) -> date | None:
        return self._date

    def set_date(self, d: date) -> None:
        self._date = d
        self._lbl.configure(text=d.strftime("%d/%m/%Y"), text_color=TEXT_PRIMARY)
