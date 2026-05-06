"""Paleta de colores y configuración de apariencia CustomTkinter."""

from __future__ import annotations

import customtkinter as ctk

# Paleta
BLUE_DARK = "#1F4E79"
BLUE_MID = "#2E75B6"
BLUE_LIGHT = "#BDD7EE"
GREEN = "#4CAF50"
GREEN_DARK = "#2E7D32"
YELLOW = "#FFC107"
RED = "#F44336"
RED_DARK = "#C62828"
GRAY_TEXT = "#9E9E9E"
WHITE = "#FFFFFF"

# Tamaños de fuente
FONT_TITLE = ("Segoe UI", 18, "bold")
FONT_SUBTITLE = ("Segoe UI", 13, "bold")
FONT_BODY = ("Segoe UI", 12)
FONT_SMALL = ("Segoe UI", 10)
FONT_MONO = ("Consolas", 11)

# Colores de estado
STATUS_COLORS: dict[str, str] = {
    "pending": GRAY_TEXT,
    "processing": BLUE_MID,
    "ok": GREEN,
    "warning": YELLOW,
    "error": RED,
}


def apply_theme() -> None:
    """Configura la apariencia global de CustomTkinter."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
