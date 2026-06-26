"""Parser para estados de cuenta de Banamex (Cuenta de Cheques MN y Dólares).

Diferencias respecto al parser MiCuenta (banamex.py):

* Producto: ``CUENTA DE CHEQUES MONEDA NACIONAL`` o ``CUENTA DE CHEQUES DOLARES``.
* Periodo en encabezado: ``RESUMEN DEL: 01/ENE/2024 AL 31/ENE/2024``.
* Saldo inicial: ``Saldo Anterior $1,532,156.26`` (con signo $).
* Saldo final: ``SALDO AL 31 DE ENERO DE 2024 $12,695.94``.
* Totales: ``( + ) 24 Depósitos $941,678.80`` y ``( - ) 9 Retiros $2,461,139.12``.
* Cuenta/contrato: ``CONTRATO 7532683995``.
* El formato de movimientos (``DD MMM CONCEPTO [RETIRO] [DEPOSITO] SALDO``)
  es idéntico al de MiCuenta.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from bank_parser.core.exceptions import FormatChangedError, ParseError
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

# "RESUMEN DEL: 01/ENE/2024 AL 31/ENE/2024"
_PERIODO_RE = re.compile(
    r"RESUMEN\s+DEL:\s+(\d{1,2})/([A-Z]{3})/(\d{4})\s+AL\s+(\d{1,2})/([A-Z]{3})/(\d{4})",
    re.IGNORECASE,
)

# "Saldo Anterior $1,532,156.26"
_SALDO_ANTERIOR_RE = re.compile(r"Saldo\s+Anterior\s+\$?([\d,]+\.\d{2})", re.IGNORECASE)

# "SALDO AL 31 DE ENERO DE 2024 $12,695.94"
_SALDO_FINAL_RE = re.compile(
    r"SALDO\s+AL\s+\d+\s+DE\s+[A-Z]+\s+DE\s+\d+\s+\$?([\d,]+\.\d{2})",
    re.IGNORECASE,
)

# "( + ) 24 Depósitos $941,678.80"
_TOTAL_DEPOSITOS_RE = re.compile(
    r"\(\s*\+\s*\)\s+\d+\s+Dep[oó]sitos\s+\$?([\d,]+\.\d{2})", re.IGNORECASE
)

# "( - ) 9 Retiros $2,461,139.12"
_TOTAL_RETIROS_RE = re.compile(r"\(\s*-\s*\)\s+\d+\s+Retiros\s+\$?([\d,]+\.\d{2})", re.IGNORECASE)

# "CONTRATO 7532683995"
_CUENTA_PATTERNS = [r"CONTRATO\s+(\d{7,})"]

# Inicio de la sección de movimientos
_DETALLE_HEADER_RE = re.compile(r"FECHA\s+CONCEPTO\s+RETIROS\s+DEP[OÓ]SITOS\s+SALDO", re.IGNORECASE)

# Inicio de movimiento: "DD MMM ..."
_MOV_DATE_RE = re.compile(r"^(\d{2})\s+([A-Z]{3})\s+", re.MULTILINE)

# Moneda en formato mexicano
_CURRENCY_RE = re.compile(r"\b\d{1,3}(?:,\d{3})*\.\d{2}\b")

# Prefijos de descripción que identifican un cargo (para bloques sin saldo explícito)
_CARGO_PREFIXES: tuple[str, ...] = (
    "COMISION",
    "IVA",
    "CARGO",
    "RETIRO",
    "COBRO",
    "CHEQUE",
    "DISPOSICION",
    "ORDEN DE PAGO",
    "PAGO A TERCEROS",
    "PAGO EFECTUADO",
    "PAGO REALIZADO",
    "TRANSFERENCIA ENVIADA",
    "TRANSFERENCIA REALIZADA",
    "TRANSFERENCIA INTERNACIONAL ENVIADA",
)

# Marcadores en el cuerpo del bloque (cualquier línea) que indican cargo
_CARGO_BODY_MARKERS: tuple[str, ...] = (
    "TRASPASO ENTRE CUENTAS",
    "INCASA FACTURAS",
)

# Líneas de ruido a filtrar entre saltos de página
_NOISE_PATTERNS = [
    re.compile(r"^\d{6}\.\w+\.\w{2}\.\d{4}\.\d{2}$"),  # serial de página "000180.B61CHDA..."
    re.compile(r"^ESTADO DE CUENTA AL \d"),  # título del documento
    re.compile(r"^CLIENTE:\s+\d"),  # número de cliente
    re.compile(r"^P[á\?]gina:\s+\d+\s+de\s+\d+"),  # pie de página
    re.compile(r"^DETALLE\s+DE\s+OPERACIONES"),  # encabezado de sección
    re.compile(r"^FECHA\s+CONCEPTO\s+RETIROS"),  # encabezado de tabla
]


class BanamexChequesParser(BankParser):
    """Parser para Banamex Cuenta de Cheques (Moneda Nacional y Dólares)."""

    bank_id = BankId.BANAMEX_CHEQUES

    expected_markers: tuple[str, ...] = (
        "CUENTA DE CHEQUES",
        "RESUMEN DEL:",
        "DETALLE DE OPERACIONES",
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
                raise FormatChangedError("Banamex Cheques", marker)

        # --- Periodo ---
        m_p = _PERIODO_RE.search(pdf_text)
        if not m_p:
            raise FormatChangedError("Banamex Cheques", "RESUMEN DEL: DD/MMM/YYYY AL DD/MMM/YYYY")
        d_ini, mes_ini_s, year_ini_s, d_fin, mes_fin_s, year_fin_s = m_p.groups()
        anio_ini = int(year_ini_s)
        anio_fin = int(year_fin_s)
        mes_ini = MES_ES_ABREV.get(mes_ini_s.upper())
        mes_fin = MES_ES_ABREV.get(mes_fin_s.upper())
        if mes_ini is None or mes_fin is None:
            raise FormatChangedError("Banamex Cheques", "mes abreviado en periodo")
        periodo_inicio = date(anio_ini, mes_ini, int(d_ini))
        periodo_fin = date(anio_fin, mes_fin, int(d_fin))

        # --- Saldos ---
        m_ant = _SALDO_ANTERIOR_RE.search(pdf_text)
        if not m_ant:
            raise FormatChangedError("Banamex Cheques", "Saldo Anterior $<monto>")
        saldo_inicial = limpiar_numero(m_ant.group(1))

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
            anio_ini=anio_ini,
            anio_fin=anio_fin,
            mes_ini=mes_ini,
            mes_fin=mes_fin,
            cuenta=cuenta,
            archivo_origen=archivo_origen,
        )

        summary = StatementSummary(
            banco=BankId.BANAMEX_CHEQUES,
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
    m = re.search(
        r"(?m)^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s\.]{8,70})\s*\n[A-Z\d].*\d",
        text,
    )
    if m:
        return m.group(1).strip()
    return ""


def _is_cargo(bloque: str) -> bool:
    """Determina si el movimiento es un cargo por las palabras clave de su descripción.

    Se usa sólo cuando el bloque tiene un único número (sin saldo explícito),
    es decir, el caso típico de comisiones e IVA en cuentas Dólares.
    """
    lines = bloque.splitlines()
    if not lines:
        return False
    first = re.sub(r"^\d{2}\s+[A-Z]{3}\s+", "", lines[0]).strip().upper()
    if any(first.startswith(prefix) for prefix in _CARGO_PREFIXES):
        return True
    # Revisar el cuerpo completo del bloque (e.g. TRASPASO tras salto de página).
    # Unimos líneas con espacio para capturar frases partidas por salto de línea.
    full = " ".join(bloque.upper().split())
    return any(marker in full for marker in _CARGO_BODY_MARKERS)


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
    m = _DETALLE_HEADER_RE.search(text)
    if not m:
        raise FormatChangedError("Banamex Cheques", "FECHA CONCEPTO RETIROS DEPOSITOS SALDO")
    body = text[m.end() :]
    for marker in (
        "SALDO MINIMO REQUERIDO",
        "AHORRO FACIL",
        "Saldo Final",
        "CADENA ORIGINAL",
        "CitiService",
    ):
        idx = body.find(marker)
        if idx >= 0:
            body = body[:idx]
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
    saldo_val: Decimal | None = None
    for line in reversed(block.splitlines()):
        nums = _CURRENCY_RE.findall(line)
        if not nums:
            continue
        if not line.rstrip().endswith(nums[-1]):
            continue
        if saldo_val is None:
            if len(nums) >= 2:
                # Dos números en la misma línea: (monto, saldo) confirmados.
                return limpiar_numero(nums[-2]), limpiar_numero(nums[-1])
            # Un solo número: puede ser el saldo; seguir buscando el monto.
            saldo_val = limpiar_numero(nums[-1])
        else:
            monto = limpiar_numero(nums[-1])
            if monto == saldo_val:
                # Línea informativa que repite el importe (e.g. "IMPORTE: $X");
                # no es un monto independiente — seguir buscando hacia arriba.
                continue
            return monto, saldo_val
    if saldo_val is not None:
        # Solo un número en todo el bloque: es el monto de la operación.
        return None, saldo_val
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
    lines[0] = re.sub(r"^\d{2}\s+[A-Z]{3}\s+", "", lines[0])
    last = lines[-1].rstrip()
    if last.endswith(saldo_lit):
        last = last[: -len(saldo_lit)].rstrip()
        if monto_lit and last.endswith(monto_lit):
            last = last[: -len(monto_lit)].rstrip()
    elif monto_lit and last.endswith(monto_lit):
        # Bloque sin saldo explícito: el único número es el monto de la operación
        last = last[: -len(monto_lit)].rstrip()
    lines[-1] = last
    return " ".join(line.strip() for line in lines if line.strip())


def _extraer_movimientos(
    *,
    pdf_text: str,
    saldo_inicial: Decimal,
    anio_ini: int,
    anio_fin: int,
    mes_ini: int,
    mes_fin: int,
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
        mes_str = m_fecha.group(2)
        mes = MES_ES_ABREV.get(mes_str)
        if mes is None:
            continue

        primer_linea = bloque.splitlines()[0].upper()
        if "SALDO ANTERIOR" in primer_linea:
            saldo_prev = saldo_inicial
            continue

        # Asignar año: si el mes coincide con el de inicio y es distinto al final → año ini
        if mes == mes_ini and mes != mes_fin:
            anio = anio_ini
        else:
            anio = anio_fin

        try:
            fecha = date(anio, mes, dia)
        except ValueError:
            continue

        try:
            monto_explicito, saldo_candidate = _last_amounts_in_block(bloque)
        except ParseError:
            continue

        if monto_explicito is not None:
            # Dos números: el último es el saldo confirmado; usamos delta para abono/cargo.
            saldo = saldo_candidate
            delta = saldo - saldo_prev
            abono = max(Decimal("0"), delta)
            cargo = max(Decimal("0"), -delta)
            monto_para_desc = monto_explicito
        else:
            # Un solo número: es el monto de la operación (sin saldo en el bloque).
            # Ocurre en cuentas Dólares y en comisiones/IVA de MN.
            monto = saldo_candidate
            if _is_cargo(bloque):
                abono, cargo = Decimal("0"), monto
                saldo = saldo_prev - monto
            else:
                abono, cargo = monto, Decimal("0")
                saldo = saldo_prev + monto
            monto_para_desc = monto

        saldo_lit = _find_literal_for(bloque, saldo)
        monto_lit = _find_literal_for(bloque, monto_para_desc)
        descripcion = _build_descripcion(bloque, monto_lit, saldo_lit)

        movimientos.append(
            Movement(
                fecha=fecha,
                descripcion=descripcion,
                abono=abono,
                cargo=cargo,
                saldo=saldo,
                banco=BankId.BANAMEX_CHEQUES,
                cuenta=cuenta,
                archivo_origen=archivo_origen,
            )
        )
        saldo_prev = saldo

    return movimientos
