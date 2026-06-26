"""Parser para estados de cuenta de Banco Santander México (Cuenta E-PYME).

Estructura del PDF:

* Encabezado sin espacios: ``ESTADODECUENTAINTEGRAL``.
* Periodo: ``PERIODO : 01 AL 31 DE ENERO DE 2024``.
* Saldos en el resumen: ``SALDO INICIAL``, ``+ DEPOSITOS``, ``- RETIROS``,
  ``= SALDO ACTUAL``.
* Tabla: ``F E C H A FOLIO DESCRIPCION DEPOSITOS RETIROS SALDO``.
* Fechas en formato ``DD-MMM-YYYY`` (p. ej. ``02-ENE-2024``).
* Las SPEI recibidas ocupan múltiples líneas; las primeras filas tienen los montos.
* Saltos de página intercalan líneas de ruido y repiten el encabezado de tabla.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from bank_parser.core.exceptions import FormatChangedError, ParseError
from bank_parser.core.schema import BankId, Movement, Statement, StatementSummary
from bank_parser.parsers._common import (
    MES_ES_ABREV,
    MES_ES_LARGO,
    extract_first_match,
    limpiar_numero,
)
from bank_parser.parsers.base import BankParser

# ---------------------------------------------------------------------------
# Patrones
# ---------------------------------------------------------------------------

# "PERIODO : 01 AL 31 DE ENERO DE 2024"
_PERIODO_RE = re.compile(
    r"PERIODO\s*:\s*(\d{1,2})\s+AL\s+(\d{1,2})\s+DE\s+([A-Z]+)\s+DE\s+(\d{4})",
    re.IGNORECASE,
)

# "SALDO INICIAL 41,892.46"
_SALDO_INICIAL_RE = re.compile(r"SALDO\s+INICIAL\s+([\d,]+\.\d{2})", re.IGNORECASE)

# "= SALDO ACTUAL 305,421.07"
_SALDO_ACTUAL_RE = re.compile(r"=\s*SALDO\s+ACTUAL\s+([\d,]+\.\d{2})", re.IGNORECASE)

# "+ DEPOSITOS 567,230.85"
_TOTAL_DEPOSITOS_RE = re.compile(r"\+\s*DEP[OÓ]SITOS\s+([\d,]+\.\d{2})", re.IGNORECASE)

# "- RETIROS 303,702.24"
_TOTAL_RETIROS_RE = re.compile(r"-\s*RETIROS\s+([\d,]+\.\d{2})", re.IGNORECASE)

# "CUENTA E-PYME 92-00046568-3" o "CLABE 014233920004656830"
_CUENTA_PATTERNS = [
    r"CUENTA\s+E-PYME\s+([\d\-]+)",
    r"CLABE\s+(\d{18})",
]

# Inicio de la sección de movimientos
_DETALLE_HEADER = "DETALLEDEMOVIMIENTOSCUENTADECHEQUES"

# Inicio de cada movimiento: "DD-MMM-YYYY FOLIO ..."
_MOV_DATE_RE = re.compile(r"^(\d{2})-([A-Z]{3})-(\d{4})\s+", re.MULTILINE)

# Moneda en formato mexicano
_CURRENCY_RE = re.compile(r"\b\d{1,3}(?:,\d{3})*\.\d{2}\b")

# Ruido de salto de página
_NOISE_PATTERNS = [
    re.compile(r"^0\d{6}$"),  # ID de cliente "0369090"
    re.compile(r"^ESTADODECUENTAINTEGRAL$"),  # título del doc
    re.compile(r"^F\s+E\s+C\s+H\s+A\s+FOLIO"),  # encabezado de tabla
    re.compile(r"^HOJA\s+\d+\s+DE\s+\d+$", re.IGNORECASE),
    re.compile(r"^INFORMACIONACLIENTES$"),
    re.compile(r"^RESUMENINFORMATIVO$"),
    re.compile(r"^CUENTADECHEQUES$"),
    re.compile(r"^CUENTAE-PYME"),
    re.compile(r"^GRAFICOCUENTADECHEQUES$"),
]


class SantanderParser(BankParser):
    """Parser para estados de cuenta Santander Cuenta E-PYME."""

    bank_id = BankId.SANTANDER

    expected_markers: tuple[str, ...] = (
        "BANCO SANTANDER MEXICO",
        "ESTADODECUENTAINTEGRAL",
        "SALDO INICIAL",
    )

    def parse(
        self,
        pdf_text: str,
        *,
        pdf_bytes: bytes | None = None,
        archivo_origen: str,
    ) -> Statement:
        for marker in self.expected_markers:
            if marker.lower() not in pdf_text.lower():
                raise FormatChangedError("Santander", marker)

        # --- Periodo ---
        m_p = _PERIODO_RE.search(pdf_text)
        if not m_p:
            raise FormatChangedError("Santander", "PERIODO : DD AL DD DE MES DE AAAA")
        d_ini, d_fin, mes_str, year_str = m_p.groups()
        anio = int(year_str)
        mes = MES_ES_LARGO.get(mes_str.upper())
        if mes is None:
            raise FormatChangedError("Santander", f"mes no reconocido: {mes_str!r}")
        periodo_inicio = date(anio, mes, int(d_ini))
        periodo_fin = date(anio, mes, int(d_fin))

        # --- Saldos ---
        m_ini = _SALDO_INICIAL_RE.search(pdf_text)
        if not m_ini:
            raise FormatChangedError("Santander", "SALDO INICIAL <monto>")
        saldo_inicial = limpiar_numero(m_ini.group(1))

        m_act = _SALDO_ACTUAL_RE.search(pdf_text)
        saldo_final = limpiar_numero(m_act.group(1)) if m_act else Decimal("0")

        m_dep = _TOTAL_DEPOSITOS_RE.search(pdf_text)
        total_abonos = limpiar_numero(m_dep.group(1)) if m_dep else Decimal("0")

        m_ret = _TOTAL_RETIROS_RE.search(pdf_text)
        total_cargos = limpiar_numero(m_ret.group(1)) if m_ret else Decimal("0")

        # --- Titular, RFC, cuenta ---
        titular = _extract_titular(pdf_text)
        rfc = _extract_rfc_santander(pdf_text)
        cuenta = extract_first_match(_CUENTA_PATTERNS, pdf_text) or ""

        # --- Movimientos ---
        movimientos = _extraer_movimientos(
            pdf_text=pdf_text,
            saldo_inicial=saldo_inicial,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            cuenta=cuenta,
            archivo_origen=archivo_origen,
        )

        summary = StatementSummary(
            banco=BankId.SANTANDER,
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
# Helpers internos
# ---------------------------------------------------------------------------


def _extract_titular(text: str) -> str:
    # Usar espacio (no \s) en la clase de caracteres para evitar cruzar líneas
    m = re.search(
        r"(?m)^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ \.]{8,80})\s*\nCODIGO DE CLIENTE",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return ""


def _extract_rfc_santander(text: str) -> str | None:
    """Santander a veces inserta espacio en medio del RFC: 'IIC970404 M82'."""
    m = re.search(
        r"R\.F\.C\.?\s+([A-ZÑ&]{3,4}\d{6})\s*([A-Z\d]{3})",
        text,
        re.IGNORECASE,
    )
    if m:
        return (m.group(1) + m.group(2)).upper()
    return None


def _strip_noise(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        if any(p.match(stripped) for p in _NOISE_PATTERNS):
            continue
        out.append(line)
    return "\n".join(out)


def _slice_movements_section(text: str) -> str:
    idx = text.find(_DETALLE_HEADER)
    if idx < 0:
        raise FormatChangedError("Santander", _DETALLE_HEADER)
    body = text[idx + len(_DETALLE_HEADER) :]
    # Cortar en la línea TOTAL (sumario al final de los movimientos)
    total_m = re.search(r"(?m)^TOTAL\s+[\d,]+\.\d{2}", body)
    if total_m:
        body = body[: total_m.start()]
    else:
        for marker in ("INFORMACIONFISCAL", "INFORMACION FISCAL", "SIGNIFICADO DE ABREVIATURAS"):
            end = body.find(marker)
            if end >= 0:
                body = body[:end]
                break
    return body


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


def _last_amounts_in_block(block: str) -> tuple[Decimal | None, Decimal]:
    for line in reversed(block.splitlines()):
        nums = _CURRENCY_RE.findall(line)
        if not nums:
            continue
        if not line.rstrip().endswith(nums[-1]):
            continue
        if len(nums) >= 2:
            return limpiar_numero(nums[-2]), limpiar_numero(nums[-1])
        return None, limpiar_numero(nums[-1])
    raise ParseError(f"Bloque sin números: {block[:60]!r}")


def _find_literal_for(block: str, value: Decimal) -> str:
    s = f"{value:,.2f}"
    if s in block:
        return s
    s2 = f"{value:.2f}"
    if s2 in block:
        return s2
    return s


def _build_descripcion(block: str, monto_lit: str | None, saldo_lit: str) -> str:
    lines = block.splitlines()
    if not lines:
        return ""
    # Quitar "DD-MMM-YYYY FOLIO " del inicio de la primera línea
    lines[0] = re.sub(r"^\d{2}-[A-Z]{3}-\d{4}\s+\S+\s+", "", lines[0])
    last = lines[-1].rstrip()
    if last.endswith(saldo_lit):
        last = last[: -len(saldo_lit)].rstrip()
        if monto_lit and last.endswith(monto_lit):
            last = last[: -len(monto_lit)].rstrip()
    lines[-1] = last
    return " ".join(line.strip() for line in lines if line.strip())


def _extraer_movimientos(
    *,
    pdf_text: str,
    saldo_inicial: Decimal,
    periodo_inicio: date,
    periodo_fin: date,
    cuenta: str,
    archivo_origen: str,
) -> list[Movement]:
    section = _slice_movements_section(pdf_text)
    section = _strip_noise(section)
    bloques = _split_by_date(section)

    movimientos: list[Movement] = []
    saldo_prev = saldo_inicial

    for bloque in bloques:
        m_fecha = _MOV_DATE_RE.match(bloque)
        if not m_fecha:
            continue
        dia = int(m_fecha.group(1))
        mes_abrev = m_fecha.group(2)
        anio_mov = int(m_fecha.group(3))
        mes = MES_ES_ABREV.get(mes_abrev)
        if mes is None:
            continue

        primer_linea = bloque.splitlines()[0].upper()
        if "SALDO FINAL DEL PERIODO ANTERIOR" in primer_linea:
            continue
        if "SALDO ANTERIOR" in primer_linea:
            saldo_prev = saldo_inicial
            continue

        try:
            fecha = date(anio_mov, mes, dia)
        except ValueError:
            continue

        # Ignorar líneas fuera del periodo (saldo anterior del mes previo)
        if fecha < periodo_inicio or fecha > periodo_fin:
            continue

        try:
            monto_explicito, saldo = _last_amounts_in_block(bloque)
        except ParseError:
            continue

        delta = saldo - saldo_prev
        if delta > 0:
            abono, cargo = delta, Decimal("0")
        elif delta < 0:
            abono, cargo = Decimal("0"), -delta
        else:
            abono, cargo = Decimal("0"), Decimal("0")

        saldo_lit = _find_literal_for(bloque, saldo)
        monto_lit = (
            _find_literal_for(bloque, monto_explicito) if monto_explicito is not None else None
        )
        descripcion = _build_descripcion(bloque, monto_lit, saldo_lit)

        movimientos.append(
            Movement(
                fecha=fecha,
                descripcion=descripcion,
                abono=abono,
                cargo=cargo,
                saldo=saldo,
                banco=BankId.SANTANDER,
                cuenta=cuenta,
                archivo_origen=archivo_origen,
            )
        )
        saldo_prev = saldo

    return movimientos
