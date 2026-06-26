"""Parser para estados de cuenta de Intercam Banco (Cuenta Enlace).

Estructura del PDF:

* Título: ``ESTADO DE CUENTA ÚNICO``.
* Periodo: ``Período DEL 2024-01-01 AL 2024-01-31`` (formato ISO).
* El PDF puede contener múltiples cuentas (MN y USD); se parsea la primera
  cuenta en Moneda Nacional (``INTERCUENTA ENLACE INTERCAM``).
* Saldos del resumen: ``Saldo Inicial``, ``Saldo Final``,
  ``+ Depósitos``, ``- Retiros``.
* Tabla: ``DÍA FOLIO CONCEPTO DEPÓSITOS RETIROS SALDO``.
* Las fechas son sólo el número de día; mes y año provienen del periodo.
* Cada fila: ``DD FOLIO CONCEPTO [monto] saldo``.
* Las SPEI usan separadores ``|`` y pueden extenderse varias líneas.
* Fin de sección: línea ``Total N M S``.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from bank_parser.core.exceptions import FormatChangedError, ParseError
from bank_parser.core.schema import BankId, Movement, Statement, StatementSummary
from bank_parser.parsers._common import (
    extract_first_match,
    extract_rfc,
    limpiar_numero,
)
from bank_parser.parsers.base import BankParser

# ---------------------------------------------------------------------------
# Patrones
# ---------------------------------------------------------------------------

# "Período DEL 2024-01-01 AL 2024-01-31"
_PERIODO_RE = re.compile(
    r"Per[íi]odo\s+DEL\s+(\d{4})-(\d{2})-(\d{2})\s+AL\s+(\d{4})-(\d{2})-(\d{2})",
    re.IGNORECASE,
)

# "Saldo Inicial 4,005.89 MN"
_SALDO_INICIAL_RE = re.compile(r"Saldo\s+Inicial\s+([\d,]+\.\d{2})", re.IGNORECASE)

# "Saldo Final 15,001.32"
_SALDO_FINAL_RE = re.compile(r"Saldo\s+Final\s+([\d,]+\.\d{2})", re.IGNORECASE)

# "+ Depósitos 1,711,004.25 MN"
_TOTAL_DEPOSITOS_RE = re.compile(r"\+\s*Dep[oó]sitos\s+([\d,]+\.\d{2})", re.IGNORECASE)

# "- Retiros 1,700,008.82 MN"
_TOTAL_RETIROS_RE = re.compile(r"-\s*Retiros\s+([\d,]+\.\d{2})", re.IGNORECASE)

# Número de cuenta: "024-99474-003-9" o CLABE
_CUENTA_PATTERNS = [
    r"INTERCUENTA\s+ENLACE\s+INTERCAM\s+([\d\-]+)",
    r"CLABE\s+(\d{18})",
]

# Encabezado de la tabla de movimientos MN
_DETALLE_HEADER_RE = re.compile(
    r"D[ÍI]A\s+FOLIO\s+CONCEPTO\s+DEP[OÓ]SITOS\s+RETIROS\s+SALDO", re.IGNORECASE
)

# Inicio de movimiento en la tabla: número de día + folio (≥6 dígitos)
_MOV_ROW_RE = re.compile(r"^(\d{1,2})\s+(\d{6,})\s+", re.MULTILINE)

# Moneda en formato mexicano
_CURRENCY_RE = re.compile(r"\b\d{1,3}(?:,\d{3})*\.\d{2}\b")

# Ruido de salto de página
_NOISE_PATTERNS = [
    re.compile(r"^Hoja\s+\d+\s+de\s+\d+", re.IGNORECASE),
    re.compile(r"^ESTE DOCUMENTO"),
    re.compile(r"^ESTADO DE CUENTA"),
    re.compile(r"^Per[íi]odo DEL \d{4}"),
    re.compile(r"^N[úu]mero\s+\d"),
    re.compile(r"^Cliente\s+\d"),
    re.compile(r"^R\.F\.C\."),
    re.compile(r"^Fecha\s+de\s+Corte"),
    re.compile(r"^Fecha\s+expedici[oó]n"),
    re.compile(r"^Sucursal\s+\w"),
    re.compile(r"^Hora\s+expedici[oó]n"),
    re.compile(r"^Versi[oó]n\s+\d"),
    re.compile(r"^Saldo\s+m[íi]nimo\s+requerido"),
    re.compile(r"^D[ÍI]A\s+FOLIO\s+CONCEPTO"),
    re.compile(r"^\*\d+\*$"),
    re.compile(r"^A[ñn]o\s+\d{4}"),
    re.compile(r"^\|$"),  # separador pipe solo
]


class IntercamParser(BankParser):
    """Parser para estados de cuenta Intercam Banco Cuenta Enlace."""

    bank_id = BankId.INTERCAM

    expected_markers: tuple[str, ...] = (
        "INTERCUENTA ENLACE INTERCAM",
        "Saldo Inicial",
        "Saldo Final",
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
                raise FormatChangedError("Intercam", marker)

        # --- Periodo ---
        m_p = _PERIODO_RE.search(pdf_text)
        if not m_p:
            raise FormatChangedError("Intercam", "Período DEL YYYY-MM-DD AL YYYY-MM-DD")
        anio_ini, mes_ini, d_ini, anio_fin, mes_fin, d_fin = (int(g) for g in m_p.groups())
        periodo_inicio = date(anio_ini, mes_ini, d_ini)
        periodo_fin = date(anio_fin, mes_fin, d_fin)

        # --- Saldos de la cuenta MN ---
        # El resumen de la cuenta MN aparece antes de la tabla de movimientos MN.
        # Usamos la primera ocurrencia (MN), que aparece antes que la USD.
        m_ini = _SALDO_INICIAL_RE.search(pdf_text)
        if not m_ini:
            raise FormatChangedError("Intercam", "Saldo Inicial <monto>")
        saldo_inicial = limpiar_numero(m_ini.group(1))

        m_fin = _SALDO_FINAL_RE.search(pdf_text)
        saldo_final = limpiar_numero(m_fin.group(1)) if m_fin else Decimal("0")

        m_dep = _TOTAL_DEPOSITOS_RE.search(pdf_text)
        total_abonos = limpiar_numero(m_dep.group(1)) if m_dep else Decimal("0")

        m_ret = _TOTAL_RETIROS_RE.search(pdf_text)
        total_cargos = limpiar_numero(m_ret.group(1)) if m_ret else Decimal("0")

        # --- Titular, RFC, cuenta ---
        titular = _extract_titular(pdf_text)
        rfc = extract_rfc(pdf_text)
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
            banco=BankId.INTERCAM,
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
    # La razón social aparece antes del domicilio (línea con "MARIANO" o que contiene dígitos)
    # Usar espacio literal (no \s) para no cruzar líneas
    m = re.search(
        r"(?m)^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{8,80})\s*\n(?:MARIANO|[A-Z]{3,}.*\d)",
        text,
    )
    if m:
        return m.group(1).strip()
    return ""


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


def _slice_mn_section(text: str) -> str:
    """Aísla la primera sección de movimientos MN."""
    m = _DETALLE_HEADER_RE.search(text)
    if not m:
        raise FormatChangedError("Intercam", "DÍA FOLIO CONCEPTO DEPÓSITOS RETIROS SALDO")
    body = text[m.end() :]
    # Cortar en la línea "Total N M S" (fin de sección MN)
    total_m = re.search(r"^Total\s+[\d,]+\.\d{2}", body, re.MULTILINE | re.IGNORECASE)
    if total_m:
        body = body[: total_m.start()]
    return body


def _split_by_row(text: str) -> list[str]:
    matches = list(_MOV_ROW_RE.finditer(text))
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
    # Quitar "DD FOLIO " del inicio de la primera línea
    lines[0] = re.sub(r"^\d{1,2}\s+\d{6,}\s+", "", lines[0])
    last = lines[-1].rstrip()
    if last.endswith(saldo_lit):
        last = last[: -len(saldo_lit)].rstrip()
        if monto_lit and last.endswith(monto_lit):
            last = last[: -len(monto_lit)].rstrip()
    lines[-1] = last
    # Normalizar separadores pipe de SPEI
    desc = " ".join(line.strip().rstrip("|").strip() for line in lines if line.strip())
    return desc


def _extraer_movimientos(
    *,
    pdf_text: str,
    saldo_inicial: Decimal,
    periodo_inicio: date,
    periodo_fin: date,
    cuenta: str,
    archivo_origen: str,
) -> list[Movement]:
    section = _slice_mn_section(pdf_text)
    section = _strip_noise(section)
    bloques = _split_by_row(section)

    movimientos: list[Movement] = []
    saldo_prev = saldo_inicial

    # Para Intercam, el periodo es normalmente un solo mes
    anio = periodo_inicio.year
    mes = periodo_inicio.month

    for bloque in bloques:
        m_row = _MOV_ROW_RE.match(bloque)
        if not m_row:
            continue
        dia = int(m_row.group(1))

        try:
            fecha = date(anio, mes, dia)
        except ValueError:
            continue

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
                banco=BankId.INTERCAM,
                cuenta=cuenta,
                archivo_origen=archivo_origen,
            )
        )
        saldo_prev = saldo

    return movimientos
