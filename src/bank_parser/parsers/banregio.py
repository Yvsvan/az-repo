"""Parser para estados de cuenta de Banregio (Cuenta Naranja Negocios).

Estructura del PDF (resumen):

* Encabezado de tabla: ``DIA CONCEPTO CARGOS ABONOS SALDO``.
* Fechas: sólo el día (1-31); el mes y el año se extraen del periodo en el
  encabezado de la primera página: ``del 01 al 31 de ENERO 2026``.
* Cada movimiento inicia con un número de día seguido del código de operación
  de 3 letras (``TRA``, ``INT``, ``DEP``, etc.).  La descripción puede
  continuar en líneas siguientes que NO empiezan con dígito.
* Los montos (CARGOS o ABONOS) y el SALDO aparecen al final de la
  PRIMERA línea del movimiento.
* El cargo o abono se determina por el delta del saldo respecto al anterior.
* La sección de movimientos se extiende desde el primer
  ``DIA CONCEPTO CARGOS ABONOS SALDO`` hasta ``Resumen Fiscal`` o
  ``Mensajes Importantes``.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from bank_parser.core.exceptions import FormatChangedError
from bank_parser.core.schema import BankId, Movement, Statement, StatementSummary
from bank_parser.parsers._common import (
    MES_ES_LARGO,
    extract_first_match,
    extract_rfc,
    limpiar_numero,
)
from bank_parser.parsers.base import BankParser

# ---------------------------------------------------------------------------
# Patrones
# ---------------------------------------------------------------------------

# "del 01 al 31 de ENERO 2026"
_PERIODO_RE = re.compile(
    r"del\s+(\d{1,2})\s+al\s+(\d{1,2})\s+de\s+([A-ZÁÉÍÓÚÑ]+)\s+(\d{4})",
    re.IGNORECASE,
)

_SALDO_INI_RE = re.compile(r"Saldo\s+Inicial\s+([\d,]+\.\d{2})", re.IGNORECASE)

# Saldo final desde Gráfico Transaccional: "= Saldo Final $21,503.21"
_SALDO_FIN_RE = re.compile(r"=\s*Saldo Final\s*\$([\d,]+\.\d{2})")

# Totales desde línea "Total X Y Z" (CARGOS ABONOS SALDO)
_TOTAL_LINE_RE = re.compile(
    r"^Total\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})",
    re.MULTILINE,
)

# RFC del cliente: "RFC: CEL810729LY8" (con dos puntos)
_RFC_CLIENTE_RE = re.compile(r"RFC:\s*([A-Z&]{3,4}\d{6}[A-Z\d]{3})")

_CUENTA_PATTERNS = [
    r"CUENTA NARANJA NEGOCIOS?\s+FLEX\s+([\d\-]+)",
    r"177-\d{5}-(\d{3}-\d+)",
    r"CLABE\s+([\d]+)",
]

_DETALLE_HEADER = "DIA CONCEPTO CARGOS ABONOS SALDO"
_SECTION_END_MARKERS = ["Resumen Fiscal", "Mensajes Importantes", "INFORMACION RELEVANTE"]

# Inicio de movimiento: "DD TRA ", "5 INT ", etc.
_MOV_DATE_RE = re.compile(r"^(\d{1,2})\s+([A-Z]{3})\s+", re.MULTILINE)

_CURRENCY_RE = re.compile(r"\b\d{1,3}(?:,\d{3})*\.\d{2}\b")

_NOISE_PATTERNS = [
    re.compile(r"^Banco Regional,?\s+S\.A\."),
    re.compile(r"^ESTADO DE CUENTA"),
    re.compile(r"^AV\.\s+PEDRO RAMIREZ"),
    re.compile(r"^SAN PEDRO GARZA"),
    re.compile(r"^R\.F\.C\.\s+BRM"),
    re.compile(r"^Centro de Atenci[oó]n"),
    re.compile(r"^Page\s+\d+\s+of\s+\d+"),
    re.compile(r"^DIA CONCEPTO CARGOS ABONOS SALDO\s*$"),
    re.compile(r"^\*\d{10}\*"),
    re.compile(r"^Comisiones Efectivamente Cobradas"),
    re.compile(r"^Saldo Inicial\s"),
    re.compile(r"^CUENTA NARANJA NEGOCIOS"),
    re.compile(r"^CLABE\s+\d"),
    re.compile(r"^CUENTA\s+TASA\s+COMISION"),
    re.compile(r"^177\d{9,}"),  # account number lines
    re.compile(r"^\"La GAT real"),
    re.compile(r"^PESOS\s*$"),
]


class BanregioParser(BankParser):
    """Parser para estados de cuenta Banregio Cuenta Naranja Negocios."""

    bank_id = BankId.BANREGIO

    expected_markers: tuple[str, ...] = (
        "Banco Regional",
        "Banregio Grupo Financiero",
        _DETALLE_HEADER,
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
                raise FormatChangedError("Banregio", marker)

        # Periodo
        m_p = _PERIODO_RE.search(pdf_text)
        if not m_p:
            raise FormatChangedError("Banregio", "del DD al DD de MES AAAA")
        d_ini, d_fin, mes_s, anio_s = m_p.groups()
        anio = int(anio_s)
        mes = MES_ES_LARGO.get(mes_s.upper(), 1)
        periodo_inicio = date(anio, mes, int(d_ini))
        periodo_fin = date(anio, mes, int(d_fin))

        # Saldo inicial
        m_ini = _SALDO_INI_RE.search(pdf_text)
        if not m_ini:
            raise FormatChangedError("Banregio", "Saldo Inicial X")
        saldo_inicial = limpiar_numero(m_ini.group(1))

        # Saldo final desde Gráfico Transaccional
        m_fin = _SALDO_FIN_RE.search(pdf_text)
        saldo_final = limpiar_numero(m_fin.group(1)) if m_fin else Decimal("0")

        # Totales desde línea "Total CARGOS ABONOS SALDO"
        m_total = _TOTAL_LINE_RE.search(pdf_text)
        if m_total:
            total_cargos = limpiar_numero(m_total.group(1))
            total_abonos = limpiar_numero(m_total.group(2))
        else:
            total_abonos = Decimal("0")
            total_cargos = Decimal("0")

        # RFC del cliente (RFC: con dos puntos) y cuenta
        m_rfc = _RFC_CLIENTE_RE.search(pdf_text)
        rfc = m_rfc.group(1) if m_rfc else extract_rfc(pdf_text)
        cuenta = extract_first_match(_CUENTA_PATTERNS, pdf_text) or ""

        # Titular
        titular = _extract_titular(pdf_text)

        # Movimientos
        movimientos = _extraer_movimientos(
            pdf_text=pdf_text,
            saldo_inicial=saldo_inicial,
            anio=anio,
            mes=mes,
            cuenta=cuenta,
            archivo_origen=archivo_origen,
        )

        summary = StatementSummary(
            banco=BankId.BANREGIO,
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
    # Buscar nombre de empresa antes del RFC
    m = re.search(
        r"(?m)^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s\.]{5,60})\s*\nRFC:\s*[A-Z]",
        text,
    )
    if m:
        return m.group(1).strip()
    # Buscar antes de AVENIDA o CP:
    m2 = re.search(
        r"(?m)^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s\.]{5,60})\n(?:AVENIDA|AV\.\s|C\.P\.:)",
        text,
    )
    if m2:
        return m2.group(1).strip()
    return ""


def _slice_movements(text: str) -> str:
    start = text.find(_DETALLE_HEADER)
    if start < 0:
        raise FormatChangedError("Banregio", _DETALLE_HEADER)
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
    anio: int,
    mes: int,
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

        try:
            fecha = date(anio, mes, dia)
        except ValueError:
            continue

        # Montos al final de la primera línea
        first_line = bloque.splitlines()[0]
        nums = _CURRENCY_RE.findall(first_line)
        if not nums:
            continue

        saldo = limpiar_numero(nums[-1])
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

        # Descripción
        desc = re.sub(r"^\d{1,2}\s+[A-Z]{3}\s+", "", first_line)
        for n in reversed(nums):
            if desc.rstrip().endswith(n):
                desc = desc[: desc.rstrip().rfind(n)].rstrip()
        descripcion = desc.strip()

        movimientos.append(
            Movement(
                fecha=fecha,
                descripcion=descripcion,
                abono=abono,
                cargo=cargo,
                saldo=saldo,
                banco=BankId.BANREGIO,
                cuenta=cuenta,
                archivo_origen=archivo_origen,
            )
        )
        saldo_prev = saldo

    return movimientos
