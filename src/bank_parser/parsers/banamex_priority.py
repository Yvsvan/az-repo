"""Parser para estados de cuenta de Banamex (Cuenta Priority).

Estructura del PDF:

* Encabezado de tabla: ``FECHA CONCEPTO RETIROS DEPÓSITOS SALDO``.
* Fechas en formato ``DD MMM`` con mes en español abreviado (``01 ABR``).
* Período en formato ``Período Del D al D de MES del AAAA`` (mismo mes).
* Cada movimiento ocupa N líneas; la última termina con el saldo
  (y opcionalmente el monto). Si el monto no aparece, se infiere por
  delta del saldo anterior.
* La cuenta se extrae de ``Número de cuenta de cheques`` o
  ``Número de contrato``.
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
    extract_rfc,
    limpiar_numero,
)
from bank_parser.parsers.base import BankParser

# ---------------------------------------------------------------------------
# Patrones
# ---------------------------------------------------------------------------

# "Período Del 1 al 30 de abril del 2026"
_PERIODO_RE = re.compile(
    r"Per[ií]odo\s+[Dd]el?\s+(\d{1,2})\s+al\s+(\d{1,2})\s+de\s+"
    r"([A-Za-z\xe1\xe9\xed\xf3\xfa\xf1\xc1\xc9\xcd\xd3\xda\xd1]+)"
    r"\s+del?\s+(\d{4})",
    re.IGNORECASE,
)

# "Saldo anterior En Pesos Moneda Nacional 24,944.79"
# También cubre el formato corto "Saldo anterior 24,944.79"
_SALDO_ANTERIOR_RE = re.compile(
    r"Saldo\s+anterior\s+(?:En\s+Pesos?\s+(?:Moneda\s+Nacional)?\s*)?([\d,]+\.\d{2})",
    re.IGNORECASE,
)

# "Saldo al corte 105,221.06"
_SALDO_AL_CORTE_RE = re.compile(r"Saldo\s+al\s+corte\s+([\d,]+\.\d{2})", re.IGNORECASE)

# "(+) 5 Depósitos 218,800.80"
_TOTAL_DEPOSITOS_RE = re.compile(r"\(\+\)\s+\d*\s*Dep[oó]sitos\s+([\d,]+\.\d{2})", re.IGNORECASE)

# "(-) 35Retiros/compras/comis./otros cargos 138,524.53"
# Nota: sin espacio entre el número de movimientos y "Retiros"
_TOTAL_RETIROS_RE = re.compile(r"\(-\)\s+\d*\s*Retiros[\w\s/.,]*\s+([\d,]+\.\d{2})", re.IGNORECASE)

_CUENTA_PATTERNS = [
    r"N[úu]mero\s+de\s+cuenta\s+de\s+cheques\s+(\d+)",
    r"N[úu]mero\s+de\s+contrato\s+(\d+)",
]

# Encabezado de la tabla de movimientos (regex para tolerar encoding del PDF)
_DETALLE_HEADER_RE = re.compile(r"FECHA\s+CONCEPTO\s+RETIROS\s+DEP[OÓ]SITOS\s+SALDO", re.IGNORECASE)

# Líneas de ruido a filtrar (encabezados/pies de página)
_NOISE_PATTERNS = [
    re.compile(r"^P[áa\?�]gina\s+\d+\s+de\s+\d+"),
    re.compile(r"^FECHA\s+CONCEPTO\s+RETIROS"),
    re.compile(r"^Detalle\s+de\s+Operaciones"),
    re.compile(r"^Centro\s+de\s+Atenci"),
    re.compile(r"^Ciudad\s+de\s+M"),
    re.compile(r"^Otra\s+ciudad"),
    re.compile(r"^E\.U\.A"),
    re.compile(r"^Otro\s+pa[íi\?�]s"),
    re.compile(r"^Cuenta\s+Priority\s*$"),
    re.compile(r"^Estado\s+de\s+Cuenta\s*$"),
    re.compile(r"^Resumen\s+del\s+\d"),
    re.compile(r"^N[úu\?�]mero\s+de\s+contrato\s+\d"),
    re.compile(r"^\d{6}\.\w+\.\w{2}\.\d+"),  # "000181.B61INDL001.AR.0430.01"
    re.compile(r"^\d{7}\s*$"),  # "0000182"
]

# Línea que empieza un movimiento: "DD MMM ..."
_MOV_DATE_RE = re.compile(r"^(\d{2})\s+([A-Z]{3})\s+", re.MULTILINE)

# Número con formato monetario mexicano
_CURRENCY_RE = re.compile(r"\b\d{1,3}(?:,\d{3})*\.\d{2}\b")


class BanamexPriorityParser(BankParser):
    """Parser para estados de cuenta Banamex Cuenta Priority."""

    bank_id = BankId.BANAMEX_PRIORITY

    expected_markers: tuple[str, ...] = (
        "Cuenta Priority",
        "Saldo anterior",
        "Saldo al corte",
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
                raise FormatChangedError("Banamex Priority", marker)

        # --- Periodo ---
        m_p = _PERIODO_RE.search(pdf_text)
        if not m_p:
            raise FormatChangedError("Banamex Priority", "Período Del D al D de MES del AAAA")
        d_ini, d_fin, mes_str, year_str = m_p.groups()
        anio = int(year_str)
        mes = MES_ES_LARGO.get(mes_str.upper())
        if mes is None:
            raise FormatChangedError("Banamex Priority", f"mes no reconocido: {mes_str!r}")
        periodo_inicio = date(anio, mes, int(d_ini))
        periodo_fin = date(anio, mes, int(d_fin))

        # --- Saldos ---
        m_ant = _SALDO_ANTERIOR_RE.search(pdf_text)
        if not m_ant:
            raise FormatChangedError("Banamex Priority", "Saldo anterior <monto>")
        saldo_inicial = limpiar_numero(m_ant.group(1))

        m_corte = _SALDO_AL_CORTE_RE.search(pdf_text)
        saldo_final = limpiar_numero(m_corte.group(1)) if m_corte else Decimal("0")

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
            anio=anio,
            mes=mes,
            cuenta=cuenta,
            archivo_origen=archivo_origen,
        )

        summary = StatementSummary(
            banco=BankId.BANAMEX_PRIORITY,
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
    """Extrae el titular: nombre en mayúsculas seguido de una línea con dirección."""
    m = re.search(
        r"(?m)^([A-Z\xd1\xc1\xc9\xcd\xd3\xda][A-Z\xd1\xc1\xc9\xcd\xd3\xda\s]{8,60})"
        r"\s*\n[A-Z0-9\xd1\xc1\xc9\xcd\xd3\xda].*\d",
        text,
    )
    if m:
        return m.group(1).strip()
    return ""


def _strip_noise(text: str) -> str:
    """Elimina líneas de encabezado/pie de página repetidas entre páginas."""
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
    """Aísla la sección de movimientos desde el encabezado de tabla."""
    m = _DETALLE_HEADER_RE.search(text)
    if not m:
        raise FormatChangedError("Banamex Priority", "FECHA CONCEPTO RETIROS DEPÓSITOS SALDO")
    body = text[m.end() :]
    # Marcadores que indican el fin de la sección de movimientos
    for marker in (
        "Cadena Original del Complemento",  # firma digital CFDI (siempre al final)
        "CONCEPTOS\n",  # sección de facturación CFDI
        "Saldo Final",
        "AHORRO FACIL",
    ):
        idx = body.find(marker)
        if idx >= 0:
            body = body[:idx]
            break
    return body


def _split_by_date(text: str) -> list[str]:
    """Devuelve bloques de texto, uno por movimiento (separado por fecha)."""
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
    """Extrae (monto_opcional, saldo) del bloque buscando en la última línea con números."""
    for line in reversed(block.splitlines()):
        nums = _CURRENCY_RE.findall(line)
        if not nums:
            continue
        if not line.rstrip().endswith(nums[-1]):
            continue
        if len(nums) >= 2:
            return limpiar_numero(nums[-2]), limpiar_numero(nums[-1])
        return None, limpiar_numero(nums[-1])
    raise ParseError(f"Bloque sin números detectables: {block[:80]!r}")


def _find_literal_for(block: str, value: Decimal) -> str:
    """Busca la representación literal de ``value`` en el bloque."""
    with_comma = f"{value:,.2f}"
    if with_comma in block:
        return with_comma
    no_comma = f"{value:.2f}"
    if no_comma in block:
        return no_comma
    return with_comma


def _build_descripcion(block: str, monto_lit: str | None, saldo_lit: str) -> str:
    """Junta líneas de descripción quitando fecha y números finales."""
    lines = block.splitlines()
    if not lines:
        return ""
    lines[0] = re.sub(r"^\d{2}\s+[A-Z]{3}\s+", "", lines[0])
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
    anio: int,
    mes: int,
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
        mes_bloque = MES_ES_ABREV.get(m_fecha.group(2))
        if mes_bloque is None:
            continue

        # Ignorar la línea "SALDO ANTERIOR"
        if "SALDO ANTERIOR" in bloque.splitlines()[0].upper():
            saldo_prev = saldo_inicial
            continue

        try:
            fecha = date(anio, mes_bloque, dia)
        except ValueError:
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
                banco=BankId.BANAMEX_PRIORITY,
                cuenta=cuenta,
                archivo_origen=archivo_origen,
            )
        )
        saldo_prev = saldo

    return movimientos
