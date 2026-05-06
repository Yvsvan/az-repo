"""Parser para estados de cuenta de Banorte (Enlace Negocios).

Estructura del PDF (resumen):

* Viene dentro de un ZIP con nombre ``DDDDDDDDDD_AAAAMMDD.PDF``.
* Encabezado de tabla:
  ``FECHA DESCRIPCIÓN / ESTABLECIMIENTO MONTO DEL DEPOSITO MONTO DEL RETIRO SALDO``
* Fechas en formato ``DD-MMM-YY`` (año de 2 dígitos), directamente
  concatenadas con la descripción sin espacio (p. ej. ``02-ENE-26SPEI…``).
* La primera línea de cada movimiento contiene los montos al final;
  las siguientes son detalle de la transacción.
* La sección de movimientos de la cuenta principal termina donde empieza
  ``INVERSION ENLACE NEGOCIOS``.
* La línea ``SALDO ANTERIOR`` contiene el saldo inicial; se omite como
  transacción.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from bank_parser.core.exceptions import FormatChangedError
from bank_parser.core.schema import BankId, Movement, Statement, StatementSummary
from bank_parser.parsers._common import (
    MES_ES_ABREV,
    extract_first_match,
    extract_rfc,
    limpiar_numero,
)
from bank_parser.parsers.base import BankParser

# ---------------------------------------------------------------------------
# Patrones
# ---------------------------------------------------------------------------

# "Periodo Del 01/Enero/2026 al 31/Enero/2026"
_PERIODO_RE = re.compile(
    r"Periodo\s+Del\s+(\d{1,2})/([A-Za-zñÑáéíóúÁÉÍÓÚ]+)/(\d{4})"
    r"\s+al\s+(\d{1,2})/([A-Za-zñÑáéíóúÁÉÍÓÚ]+)/(\d{4})",
    re.IGNORECASE,
)

_SALDO_INI_RE = re.compile(r"Saldo\s+inicial\s+del\s+periodo\s*\$\s*([\d,]+\.\d{2})", re.IGNORECASE)
_SALDO_FIN_RE = re.compile(r"Saldo\s+actual\s*\$\s*([\d,]+\.\d{2})", re.IGNORECASE)
_TOTAL_DEP_RE = re.compile(r"Total\s+de\s+dep[oó]sitos\s*\$\s*([\d,]+\.\d{2})", re.IGNORECASE)

_CUENTA_PATTERNS = [
    r"ENLACE\s+NEGOCIOS\s+BASICA\s+(\d+)",
    r"ENLACE\s+NEGOCIOS\s+\w+\s+(\d+)",
    r"NO\.\s+DE\s+CUENTA[:\s]+(\d{10,})",
]

_DETALLE_HEADER = "FECHA DESCRIPCIÓN / ESTABLECIMIENTO MONTO DEL DEPOSITO MONTO DEL RETIRO SALDO"
_SECTION_END_MARKERS = ["INVERSION ENLACE NEGOCIOS", "OTROS▼", "OTROS\n"]

# DD-MMM-YY al inicio de línea (directamente pegado a la descripción)
_MOV_DATE_RE = re.compile(r"^(\d{2})-([A-Z]{3})-(\d{2})", re.MULTILINE)

_CURRENCY_RE = re.compile(r"\b\d{1,3}(?:,\d{3})*\.\d{2}\b")

_NOISE_PATTERNS = [
    re.compile(r"^ESTADO DE CUENTA\s*/\s*ENLACE"),
    re.compile(r"^DETALLE DE MOVIMIENTOS"),
    re.compile(r"^Enlace Negocios\s+Basica\s*$", re.IGNORECASE),
    re.compile(r"^FECHA DESCRIPCI[OÓ]N\s*/\s*ESTABLECIMIENTO"),
    re.compile(r"^P[aá]gina\s+\d+"),
    re.compile(r"^PAGINA\s+\d+"),
]

# Meses en español en formato largo para el encabezado del periodo
_MES_ES_LARGO_BANORTE = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}


class BanorteParser(BankParser):
    """Parser para estados de cuenta Banorte Enlace Negocios."""

    bank_id = BankId.BANORTE

    expected_markers: tuple[str, ...] = (
        "ENLACE NEGOCIOS",
        "Banco Mercantil del Norte",
        "Saldo inicial del periodo",
    )

    def parse(
        self,
        pdf_text: str,
        *,
        pdf_bytes: bytes | None = None,
        archivo_origen: str,
    ) -> Statement:
        for marker in self.expected_markers:
            if marker not in pdf_text:
                raise FormatChangedError("Banorte", marker)

        # Periodo
        m_periodo = _PERIODO_RE.search(pdf_text)
        if not m_periodo:
            raise FormatChangedError("Banorte", "Periodo Del DD/MES/AAAA al DD/MES/AAAA")
        d_ini, mes_ini_s, anio_ini_s, d_fin, mes_fin_s, anio_fin_s = m_periodo.groups()
        anio_ini = int(anio_ini_s)
        anio_fin = int(anio_fin_s)
        mes_ini = _MES_ES_LARGO_BANORTE.get(mes_ini_s.upper(), 1)
        mes_fin = _MES_ES_LARGO_BANORTE.get(mes_fin_s.upper(), 1)
        periodo_inicio = date(anio_ini, mes_ini, int(d_ini))
        periodo_fin = date(anio_fin, mes_fin, int(d_fin))

        # Saldos
        m_ini = _SALDO_INI_RE.search(pdf_text)
        if not m_ini:
            raise FormatChangedError("Banorte", "Saldo inicial del periodo $X")
        saldo_inicial = limpiar_numero(m_ini.group(1))

        m_fin = _SALDO_FIN_RE.search(pdf_text)
        saldo_final = limpiar_numero(m_fin.group(1)) if m_fin else Decimal("0")

        m_dep = _TOTAL_DEP_RE.search(pdf_text)
        total_abonos = limpiar_numero(m_dep.group(1)) if m_dep else Decimal("0")
        total_cargos = saldo_inicial + total_abonos - saldo_final

        # RFC y cuenta
        rfc = extract_rfc(pdf_text)
        cuenta = extract_first_match(_CUENTA_PATTERNS, pdf_text) or ""

        # Titular (primera línea que sea todo mayúsculas con 3+ palabras en el header)
        titular = _extract_titular(pdf_text)

        # Movimientos
        movimientos = _extraer_movimientos(
            pdf_text=pdf_text,
            saldo_inicial=saldo_inicial,
            anio_fin=anio_fin,
            cuenta=cuenta,
            archivo_origen=archivo_origen,
        )

        summary = StatementSummary(
            banco=BankId.BANORTE,
            titular=titular,
            rfc=rfc,
            cuenta=cuenta,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            saldo_inicial=saldo_inicial,
            saldo_final=saldo_final,
            total_abonos=total_abonos,
            total_cargos=total_cargos,
            archivo_origen=archivo_origen,
        )
        return Statement(summary=summary, movements=movimientos)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_titular(text: str) -> str:
    # Buscar línea con nombre en mayúsculas antes de "CIUDAD INDUSTRIAL" o similar
    m = re.search(
        r"(?m)^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{5,60}(?:S\.A\. DE C\.V\.|SA DE CV|S\.C\.|S\.A\.))\s*$",
        text,
    )
    if m:
        return m.group(1).strip()
    # Fallback: segunda línea del header (empresa / persona)
    m2 = re.search(r"(?m)^((?:[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{3,}){2,})\n(?:AVENIDA|CALLE|AV\.|C\.)", text)
    if m2:
        return m2.group(1).strip()
    return ""


def _parse_date_banorte(dd: str, mes_str: str, yy: str, year_fin: int) -> date | None:
    mes = MES_ES_ABREV.get(mes_str)
    if mes is None:
        return None
    yr_2digit = int(yy)
    # Año de base: el siglo del año de fin del periodo
    year = (year_fin // 100) * 100 + yr_2digit
    if year > year_fin:
        year -= 100
    try:
        return date(year, mes, int(dd))
    except ValueError:
        return None


def _slice_movements(text: str) -> str:
    start = text.find(_DETALLE_HEADER)
    if start < 0:
        raise FormatChangedError("Banorte", _DETALLE_HEADER)
    body = text[start + len(_DETALLE_HEADER) :]
    for end_marker in _SECTION_END_MARKERS:
        idx = body.find(end_marker)
        if idx >= 0:
            body = body[:idx]
            break
    return body


def _strip_noise(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and any(p.match(stripped) for p in _NOISE_PATTERNS):
            continue
        out.append(line)
    return "\n".join(out)


def _split_by_date(text: str) -> list[str]:
    matches = list(_MOV_DATE_RE.finditer(text))
    if not matches:
        return []
    blocks: list[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append(text[start:end])
    return blocks


def _extraer_movimientos(
    *,
    pdf_text: str,
    saldo_inicial: Decimal,
    anio_fin: int,
    cuenta: str,
    archivo_origen: str,
) -> list[Movement]:
    section = _slice_movements(pdf_text)
    section = _strip_noise(section)
    bloques = _split_by_date(section)

    movimientos: list[Movement] = []
    saldo_prev = saldo_inicial

    for bloque in bloques:
        m_fecha = _MOV_DATE_RE.match(bloque)
        if not m_fecha:
            continue
        dd, mes_str, yy = m_fecha.group(1), m_fecha.group(2), m_fecha.group(3)

        # Saltar "SALDO ANTERIOR"
        first_line = bloque.splitlines()[0]
        if "SALDO ANTERIOR" in first_line.upper():
            continue

        fecha = _parse_date_banorte(dd, mes_str, yy, anio_fin)
        if fecha is None:
            continue

        # Montos: están al final de la PRIMERA línea del bloque
        nums_en_primera = _CURRENCY_RE.findall(first_line)
        if not nums_en_primera:
            continue

        saldo = limpiar_numero(nums_en_primera[-1])
        delta = saldo - saldo_prev
        if delta > 0:
            abono = delta
            cargo = Decimal("0")
        elif delta < 0:
            abono = Decimal("0")
            cargo = -delta
        else:
            abono = Decimal("0")
            cargo = Decimal("0")

        # Descripción: primera línea sin fecha ni números finales + resto del bloque
        desc_line = re.sub(r"^\d{2}-[A-Z]{3}-\d{2}", "", first_line).strip()
        # Eliminar los montos al final
        for num in reversed(nums_en_primera):
            if desc_line.endswith(num):
                desc_line = desc_line[: -len(num)].rstrip()
        # Añadir líneas de detalle (opcional)
        extra_lines = bloque.splitlines()[1:]
        extra = " ".join(line.strip() for line in extra_lines if line.strip())
        descripcion = (desc_line + (" " + extra if extra else "")).strip()

        movimientos.append(
            Movement(
                fecha=fecha,
                descripcion=descripcion,
                abono=abono,
                cargo=cargo,
                saldo=saldo,
                banco=BankId.BANORTE,
                cuenta=cuenta,
                archivo_origen=archivo_origen,
            )
        )
        saldo_prev = saldo

    return movimientos
