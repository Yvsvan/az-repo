"""Paleta de colores y configuración de apariencia CustomTkinter."""

from __future__ import annotations

import customtkinter as ctk

# ── Superficies / fondos ─────────────────────────────────────────────────────
BG_APP = "#0F172A"  # slate-900 - fondo global de la ventana
BG_SURFACE = "#1E293B"  # slate-800 - paneles, action bars, headers
BG_ELEVATED = "#263044"  # ligeramente elevado - cards, hover
BG_INPUT = "#1A2535"  # inputs / textboxes

# ── Bordes ───────────────────────────────────────────────────────────────────
BORDER_DEFAULT = "#334155"  # slate-700
BORDER_ACCENT = "#0D9488"  # teal

# ── Texto ────────────────────────────────────────────────────────────────────
TEXT_PRIMARY = "#F1F5F9"  # slate-100
TEXT_SECONDARY = "#94A3B8"  # slate-400
TEXT_MUTED = "#64748B"  # slate-500

# ── Acentos / estado ─────────────────────────────────────────────────────────
TEAL = "#0D9488"  # primary accent - acciones principales
TEAL_LT = "#14B8A6"  # teal claro - hover / active
EMERALD = "#10B981"  # success
AMBER = "#F59E0B"  # warning
CRIMSON = "#EF4444"  # error
SKY = "#38BDF8"  # procesando / info

# ── Alias de retrocompatibilidad ─────────────────────────────────────────────
BLUE_DARK = BG_SURFACE
BLUE_MID = TEAL
BLUE_LIGHT = BG_ELEVATED
GREEN = EMERALD
GREEN_DARK = "#059669"
YELLOW = AMBER
RED = CRIMSON
RED_DARK = "#DC2626"
GRAY_TEXT = TEXT_SECONDARY
WHITE = TEXT_PRIMARY

# ── Fuentes ──────────────────────────────────────────────────────────────────
FONT_TITLE = ("Segoe UI", 20, "bold")
FONT_SUBTITLE = ("Segoe UI", 14, "bold")
FONT_BODY = ("Segoe UI", 13)
FONT_SMALL = ("Segoe UI", 11)
FONT_MONO = ("Consolas", 11)

# ── Colores de estado ────────────────────────────────────────────────────────
STATUS_COLORS: dict[str, str] = {
    "pending": TEXT_MUTED,
    "processing": SKY,
    "ok": EMERALD,
    "warning": AMBER,
    "error": CRIMSON,
}


def apply_theme() -> None:
    """Configura la apariencia global de CustomTkinter."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
