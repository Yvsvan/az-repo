"""Parser para estados de cuenta de BanBajío (Cuenta Conecta BanBajío).

Estructura del PDF (resumen):

* Encabezado de tabla:
  ``FECHA  DESCRIPCION DE LA OPERACION  DEPOSITOS  RETIROS  SALDO``
* Fechas en formato ``D MMM`` o ``DD MMM`` (día numérico + mes abreviado
  en español en mayúsculas), al inicio de línea.
* Cada movimiento inicia con la fecha y puede incluir varias líneas de
  detalle (``INSTITUCIÓN EMISORA``, ``ORDENANTE``, ``REFERENCIA``,
  ``HORA``, ``CLAVE DE RASTREO``).
* Los montos (DEPOSITOS / RETIROS y SALDO) aparecen al final de la
  PRIMERA línea del movimiento. Si sólo hay un monto es el SALDO (para
  la línea ``SALDO INICIAL``).
* El resumen del encabezado incluye:
  ``SALDO ANTERIOR (+) DEPOSITOS (-) CARGOS SALDO ACTUAL``
  con los cuatro montos en la línea siguiente.
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

# "PERIODO: 1 DE FEBRERO AL 28 DE FEBRERO DE 2026"
_PERIODO_RE = re.compile(
    r"PERIODO:\s*(\d{1,2})\s+DE\s+([A-ZÁÉÍÓÚÑ]+)"
    r"\s+AL\s+(\d{1,2})\s+DE\s+([A-ZÁÉÍÓÚÑ]+)\s+DE\s+(\d{4})",
    re.IGNORECASE,
)

# Cuenta: "CUENTA CONECTA BANBAJIO 0199993900201"
_CUENTA_PATTERNS = [
    r"CUENTA CONECTA BANBAJIO\s+(\d+)",
    r"CUENTA\s+CONECTA\s+BANBAJIO\s*#?\s*(\d+)",
]

# Resumen: cuatro montos en la línea "$X.XX $X.XX $X.XX $X.XX"
_RESUMEN_RE = re.compile(
    r"\$\s*([\d,]+\.\d{2})\s+\$\s*([\d,]+\.\d{2})\s+\$\s*([\d,]+\.\d{2})\s+\$\s*([\d,]+\.\d{2})"
)

_DETALLE_HEADER = "DESCRIPCION DE LA OPERACION"
_SALDO_INI_RE = re.compile(r"SALDO\s+INICIAL\s+\$\s*([\d,]+\.\d{2})", re.IGNORECASE)

# Inicio de movimiento: "D MMM" o "DD MMM" al inicio de línea
_MOV_DATE_RE = re.compile(r"^(\d{1,2})\s+([A-Z]{3})\s+", re.MULTILINE)

_CURRENCY_RE = re.compile(r"\$\s*\d{1,3}(?:,\d{3})*\.\d{2}|\b\d{1,3}(?:,\d{3})*\.\d{2}\b")
_CURRENCY_VALUE_RE = re.compile(r"[\d,]+\.\d{2}")

_NOISE_PATTERNS = [
    re.compile(r"^ESTADO DE CUENTA\s*$"),
    re.compile(r"^BANCO DEL BAJIO"),
    re.compile(r"^NUMERO DE CLIENTE"),
    re.compile(r"^R\.F\.C\."),
    re.compile(r"^NO\.\s+REF\s*\.?\s*/"),
    re.compile(r"^FECHA\s+DESCRIPCION"),
    re.compile(r"^CONTINUA EN"),
    re.compile(r"^SALDO INICIAL"),
]

_MES_ES_LARGO_BB = {
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


class BanBajioParser(BankParser):
    """Parser para estados de cuenta BanBajío Cuenta Conecta."""

    bank_id = BankId.BANBAJIO

    expected_markers: tuple[str, ...] = (
        "BANCO DEL BAJIO",
        "CUENTA CONECTA BANBAJIO",
        "DESCRIPCION DE LA OPERACION",
    )

    def parse(
        self,
        pdf_text: str,
        *,
        pdf_bytes: bytes | None = None,
        archivo_origen: str,
    ) -> Statement:
        for marker in self.expected_markers:
            if (
                marker not in pdf_text.upper().replace("Ó", "O").replace("Ú", "U")
                and marker not in pdf_text
            ):
                raise FormatChangedError("BanBajio", marker)

        # Periodo
        m_p = _PERIODO_RE.search(pdf_text)
        if not m_p:
            raise FormatChangedError("BanBajio", "PERIODO: D DE MES AL D DE MES DE AAAA")
        d_ini, mes_ini_s, d_fin, mes_fin_s, anio_s = m_p.groups()
        anio = int(anio_s)
        mes_ini = _MES_ES_LARGO_BB.get(mes_ini_s.upper(), 1)
        mes_fin = _MES_ES_LARGO_BB.get(mes_fin_s.upper(), 1)
        periodo_inicio = date(anio, mes_ini, int(d_ini))
        periodo_fin = date(anio, mes_fin, int(d_fin))

        # Resumen (saldo anterior, depósitos, cargos, saldo actual)
        m_res = _RESUMEN_RE.search(pdf_text)
        if not m_res:
            raise FormatChangedError(
                "BanBajio",
                "Línea de resumen $ X.XX $ X.XX $ X.XX $ X.XX",
            )
        saldo_inicial = limpiar_numero(m_res.group(1))
        total_abonos = limpiar_numero(m_res.group(2))
        total_cargos = limpiar_numero(m_res.group(3))
        saldo_final = limpiar_numero(m_res.group(4))

        # RFC, cuenta y titular
        rfc = extract_rfc(pdf_text)
        cuenta = extract_first_match(_CUENTA_PATTERNS, pdf_text) or ""
        titular = _extract_titular(pdf_text)

        # Movimientos
        movimientos = _extraer_movimientos(
            pdf_text=pdf_text,
            saldo_inicial=saldo_inicial,
            anio=anio,
            cuenta=cuenta,
            archivo_origen=archivo_origen,
        )

        summary = StatementSummary(
            banco=BankId.BANBAJIO,
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
    # El titular aparece antes del texto de la sucursal
    m = re.search(
        r"(?m)^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{5,60})\s*\n(?:[A-ZÁÉÍÓÚÑ\d].*\n)*.*BANCO DEL BAJIO",
        text,
    )
    if m:
        return m.group(1).strip()
    # Fallback: buscar RFC y tomar la línea anterior
    m2 = re.search(r"(?m)^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑA-Z\s,\.]{5,60})\s*\nR\.F\.C\.", text)
    if m2:
        return m2.group(1).strip()
    return ""


def _slice_movements(text: str) -> str:
    """Desde la primera ocurrencia del header de detalle hasta el fin."""
    start = text.upper().find(_DETALLE_HEADER.upper())
    if start < 0:
        raise FormatChangedError("BanBajio", _DETALLE_HEADER)
    return text[start + len(_DETALLE_HEADER) :]


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
    anio: int,
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
        dia = int(m_fecha.group(1))
        mes_str = m_fecha.group(2)
        mes = MES_ES_ABREV.get(mes_str)
        if mes is None:
            continue

        try:
            fecha = date(anio, mes, dia)
        except ValueError:
            continue

        # Montos al final de la primera línea: último $ X → saldo, penúltimo → monto
        first_line = bloque.splitlines()[0]
        dollar_nums = _CURRENCY_VALUE_RE.findall(first_line)
        if not dollar_nums:
            continue

        saldo = limpiar_numero(dollar_nums[-1])
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

        # Descripción: primera línea sin fecha ni montos
        desc = re.sub(r"^\d{1,2}\s+[A-Z]{3}\s+", "", first_line)
        for n in reversed(dollar_nums):
            # Eliminar el patrón "$ X.XX" o "X.XX" del final
            desc = re.sub(r"\s*\$?\s*" + re.escape(n) + r"\s*$", "", desc).rstrip()

        movimientos.append(
            Movement(
                fecha=fecha,
                descripcion=desc.strip(),
                abono=abono,
                cargo=cargo,
                saldo=saldo,
                banco=BankId.BANBAJIO,
                cuenta=cuenta,
                archivo_origen=archivo_origen,
            )
        )
        saldo_prev = saldo

    return movimientos
