"""Helpers reusables por todos los parsers.

Convenciones:

* Las funciones aquí son **puras** (sin estado, sin I/O). Son
  candidatas naturales para tests unitarios.
* Toda función que extrae texto del PDF devuelve ``None`` (no lanza)
  cuando el campo es opcional, y lanza :class:`ParseError` cuando es
  requerido y no se encontró.
"""

from __future__ import annotations

import re
from decimal import Decimal

from bank_parser.core.exceptions import ParseError

# ---------------------------------------------------------------------------
# Meses en español (uso en regex de fechas)
# ---------------------------------------------------------------------------
MES_ES_ABREV = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}

MES_ES_LARGO = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10,
    "NOVIEMBRE": 11, "DICIEMBRE": 12,
}


# ---------------------------------------------------------------------------
# Limpieza y conversión de números
# ---------------------------------------------------------------------------
_NUM_CLEAN_RE = re.compile(r"[\s$,]")


def limpiar_numero(s: str) -> Decimal:
    """Convierte un string con formato ``"1,234.56"`` (o ``"$1,234.56"``)
    en :class:`Decimal`. Lanza :class:`ParseError` si no es parseable.
    """
    if s is None:
        raise ParseError("Cadena numérica vacía.")
    cleaned = _NUM_CLEAN_RE.sub("", s)
    if not cleaned:
        raise ParseError(f"Cadena numérica vacía después de limpiar: {s!r}")
    try:
        return Decimal(cleaned)
    except Exception as exc:
        raise ParseError(f"No se pudo parsear número: {s!r}") from exc


# ---------------------------------------------------------------------------
# Extracción de RFC mexicano
# ---------------------------------------------------------------------------
# RFC físico: 4 letras + 6 dígitos + 3 alfanuméricos = 13.
# RFC moral:  3 letras + 6 dígitos + 3 alfanuméricos = 12.
_RFC_RE = re.compile(
    r"\b([A-ZÑ&]{3,4}\d{6}[A-Z\d]{3})\b",
    re.IGNORECASE,
)


def extract_rfc(text: str) -> str | None:
    """Devuelve el primer RFC que aparezca en el texto, o ``None``.

    No valida el dígito verificador (es difícil sin un cálculo
    completo); confía en que un patrón de 12-13 chars en el formato
    correcto es suficiente para casos reales.
    """
    m = _RFC_RE.search(text)
    return m.group(1).upper() if m else None


# ---------------------------------------------------------------------------
# Extracción de números de cuenta (heurística genérica)
# ---------------------------------------------------------------------------
def extract_first_match(patterns: list[str], text: str) -> str | None:
    """Devuelve el primer grupo capturado por cualquiera de los patrones."""
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return None
