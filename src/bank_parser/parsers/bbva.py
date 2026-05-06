"""Parser para estados de cuenta de BBVA México (CASH MANAGEMENT M.N.).

Estrategia de parsing:

* Usa ``pdfplumber`` con extracción de palabras posicionadas para
  distinguir las columnas CARGOS y ABONOS (que no son diferenciables
  por texto plano cuando ambas están presentes en la misma área).
* Para cada página con movimientos, se localiza el encabezado de
  columnas y se miden los límites de derecha (x1) de cada columna.
* Un número cuya coordenada x1 cae en la zona de CARGOS → cargo;
  en la zona de ABONOS → abono; en OPERAÇÃO o LIQUIDAÇÃO → saldo.
* Cuando la línea no tiene saldo explícito, el saldo se calcula
  acumulativamente.
* La fecha de movimiento usada es la de OPER (fecha de operación).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from io import BytesIO

import pdfplumber

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
# Patrones de texto
# ---------------------------------------------------------------------------

# "Periodo DEL 01/02/2026 AL 28/02/2026"
_PERIODO_RE = re.compile(
    r"Periodo\s+DEL\s+(\d{2})/(\d{2})/(\d{4})\s+AL\s+(\d{2})/(\d{2})/(\d{4})",
    re.IGNORECASE,
)

_SALDO_INI_RE = re.compile(
    r"Saldo\s+de\s+Liquidaci[oó]n\s+Inicial\s+([\d,]+\.\d{2})", re.IGNORECASE
)
_SALDO_FIN_RE = re.compile(r"Saldo\s+Final\s+\(\+\)\s+([\d,]+\.\d{2})", re.IGNORECASE)
_TOTAL_ABONOS_RE = re.compile(
    r"Dep[oó]sitos\s*/\s*Abonos\s*\(\+\)\s+\d+\s+([\d,]+\.\d{2})", re.IGNORECASE
)
_TOTAL_CARGOS_RE = re.compile(
    r"Retiros\s*/\s*Cargos\s*\(-\)\s+\d+\s+([\d,]+\.\d{2})", re.IGNORECASE
)

_CUENTA_PATTERNS = [
    r"No\.\s*de\s*Cuenta\s+([\d]+)",
    r"No\.\s*Cuenta\s+([\d]+)",
    r"0112826798",  # fallback para este sample específico
]

_CURRENCY_RE = re.compile(r"\b\d{1,3}(?:,\d{3})*\.\d{2}\b")

# Encabezado de la tabla de movimientos
_HEADER_KEYWORDS = frozenset(
    ["CARGOS", "ABONOS", "OPERACIÓN", "LIQUIDACIÓN", "OPERACION", "LIQUIDACION"]
)
# Línea de movimiento: empieza con DD/MMM
_MOV_LINE_RE = re.compile(r"^\s*(\d{2}/[A-Z]{3})\s+(\d{2}/[A-Z]{3})\s+(\w+)\s+(.*)")


@dataclass
class _ColBounds:
    """Límites de x1 (borde derecho) de cada columna numérica."""

    cargos_max: float = 410.0
    abonos_max: float = 470.0
    oper_max: float = 535.0
    # liq: todo lo que sea > oper_max


class BBVAParser(BankParser):
    """Parser para estados de cuenta BBVA Cash Management."""

    bank_id = BankId.BBVA

    expected_markers: tuple[str, ...] = (
        "BBVA MEXICO",
        "CASH MANAGEMENT",
        "CARGOS",
        "ABONOS",
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
                raise FormatChangedError("BBVA", marker)

        if pdf_bytes is None:
            raise ParseError("BBVA requiere pdf_bytes para el análisis de columnas.")

        # Periodo
        m_p = _PERIODO_RE.search(pdf_text)
        if not m_p:
            raise FormatChangedError("BBVA", "Periodo DEL DD/MM/AAAA AL DD/MM/AAAA")
        dd_ini, mm_ini, aaaa_ini, dd_fin, mm_fin, aaaa_fin = m_p.groups()
        periodo_inicio = date(int(aaaa_ini), int(mm_ini), int(dd_ini))
        periodo_fin = date(int(aaaa_fin), int(mm_fin), int(dd_fin))
        anio = int(aaaa_fin)

        # Saldos y totales
        m_ini = _SALDO_INI_RE.search(pdf_text)
        if not m_ini:
            raise FormatChangedError("BBVA", "Saldo de Liquidación Inicial X")
        saldo_inicial = limpiar_numero(m_ini.group(1))

        m_fin = _SALDO_FIN_RE.search(pdf_text)
        saldo_final = limpiar_numero(m_fin.group(1)) if m_fin else Decimal("0")

        m_ab = _TOTAL_ABONOS_RE.search(pdf_text)
        total_abonos = limpiar_numero(m_ab.group(1)) if m_ab else Decimal("0")

        m_ca = _TOTAL_CARGOS_RE.search(pdf_text)
        total_cargos = limpiar_numero(m_ca.group(1)) if m_ca else Decimal("0")

        # RFC y cuenta
        rfc = extract_rfc(pdf_text)
        cuenta = (
            extract_first_match([r"No\.\s*de\s*Cuenta\s+(\d+)", r"No\.\s+Cuenta\s+(\d+)"], pdf_text)
            or ""
        )

        # Titular
        titular = _extract_titular(pdf_text)

        # Movimientos (usando palabras posicionadas)
        movimientos = _extraer_movimientos(
            pdf_bytes=pdf_bytes,
            saldo_inicial=saldo_inicial,
            anio=anio,
            mes_fin=periodo_fin.month,
            cuenta=cuenta,
            archivo_origen=archivo_origen,
        )

        summary = StatementSummary(
            banco=BankId.BBVA,
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
    m = re.search(
        r"(?m)^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s\.]{5,60}(?:S\.A\. DE C\.V\.|SA DE CV|S\.C\.))\s*$", text
    )
    if m:
        return m.group(1).strip()
    # Fallback: línea antes del RFC
    m2 = re.search(r"(?m)^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s\.]{5,60})\s*\nR\.F\.C\s+", text)
    if m2:
        return m2.group(1).strip()
    return ""


def _parse_bbva_date(date_str: str, anio: int, mes_fin: int) -> date | None:
    """Convierte '01/FEB' a date usando el año del periodo."""
    parts = date_str.split("/")
    if len(parts) != 2:
        return None
    dd, mes_str = parts
    mes = MES_ES_ABREV.get(mes_str.upper())
    if mes is None:
        return None
    try:
        # Si el mes es el mismo que el mes de fin, usa el año de fin.
        # Si es diferente (ej: movimiento de DIC en reporte de ENE), puede
        # pertenecer al año anterior.
        year = anio if mes <= mes_fin else anio - 1
        return date(year, mes, int(dd))
    except ValueError:
        return None


@dataclass
class _MovRow:
    oper_date: str
    cod: str
    desc_parts: list[str] = field(default_factory=list)
    cargo: Decimal = Decimal("0")
    abono: Decimal = Decimal("0")
    oper_saldo: Decimal | None = None
    liq_saldo: Decimal | None = None


def _classify_x1(x1: float, bounds: _ColBounds) -> str:
    """Clasifica un número por su coordenada x1 en la columna correspondiente."""
    if x1 <= bounds.cargos_max:
        return "cargo"
    if x1 <= bounds.abonos_max:
        return "abono"
    if x1 <= bounds.oper_max:
        return "oper_saldo"
    return "liq_saldo"


def _extraer_movimientos(
    *,
    pdf_bytes: bytes,
    saldo_inicial: Decimal,
    anio: int,
    mes_fin: int,
    cuenta: str,
    archivo_origen: str,
) -> list[Movement]:
    movimientos: list[Movement] = []
    rows: list[_MovRow] = []

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False)
            if not words:
                continue

            # Agrupar palabras por línea (tolerancia vertical de 3 pts)
            lines_dict: dict[int, list[dict]] = {}
            for w in words:
                key = round(w["top"] / 3)
                lines_dict.setdefault(key, []).append(w)

            lines_sorted = [
                sorted(v, key=lambda w: w["x0"])
                for v in sorted(lines_dict.values(), key=lambda v: v[0]["top"])
            ]

            # Detectar límites de columnas desde la línea de encabezado de la
            # tabla de movimientos (empieza con OPER/LIQ y contiene CARGOS/ABONOS).
            # Usar esa línea específica evita que labels de otras secciones
            # (p. ej. resumen al pie de página) sobreescriban los límites.
            bounds = _ColBounds()
            for line_words in lines_sorted:
                first_text = line_words[0]["text"] if line_words else ""
                if first_text in ("OPER", "LIQ") and any(
                    w["text"] in ("CARGOS", "ABONOS") for w in line_words
                ):
                    for w in line_words:
                        if w["text"] == "CARGOS":
                            bounds.cargos_max = w["x1"] + 5
                        elif w["text"] == "ABONOS":
                            bounds.abonos_max = w["x1"] + 5
                        elif w["text"] in ("OPERACIÓN", "OPERACION"):
                            bounds.oper_max = w["x1"] + 5
                    break

            cur_row: _MovRow | None = None
            in_movements = False

            for line_words in lines_sorted:
                first_text = line_words[0]["text"] if line_words else ""

                # Detectar inicio de sección de movimientos
                if first_text in ("OPER", "LIQ") and any(
                    w["text"] in ("CARGOS", "ABONOS") for w in line_words
                ):
                    in_movements = True
                    continue

                if not in_movements:
                    continue

                # Detener al salir de la sección de movimientos
                if first_text in ("No.", "No") and any(
                    w["text"] in ("Cuenta", "Cliente") for w in line_words[1:3]
                ):
                    continue  # encabezado de página repetido

                # ¿Es una nueva línea de movimiento? (empieza con DD/MMM)
                if re.match(r"^\d{2}/[A-Z]{3}$", first_text):
                    # Guardar fila anterior
                    if cur_row is not None:
                        rows.append(cur_row)
                    # Extraer oper_date y liq_date
                    oper_date_str = first_text
                    cur_row = _MovRow(oper_date=oper_date_str, cod="")
                    # Iterar palabras de esta línea
                    word_idx = 1
                    # liq_date
                    if word_idx < len(line_words) and re.match(
                        r"^\d{2}/[A-Z]{3}$", line_words[word_idx]["text"]
                    ):
                        word_idx += 1  # skip liq_date
                    # cod
                    if word_idx < len(line_words):
                        cur_row.cod = line_words[word_idx]["text"]
                        word_idx += 1
                    # Resto: descripción y números
                    for w in line_words[word_idx:]:
                        if _CURRENCY_RE.match(w["text"]):
                            col = _classify_x1(w["x1"], bounds)
                            if col == "cargo":
                                cur_row.cargo += limpiar_numero(w["text"])
                            elif col == "abono":
                                cur_row.abono += limpiar_numero(w["text"])
                            elif col == "oper_saldo":
                                cur_row.oper_saldo = limpiar_numero(w["text"])
                            else:
                                cur_row.liq_saldo = limpiar_numero(w["text"])
                        else:
                            cur_row.desc_parts.append(w["text"])

                elif cur_row is not None:
                    # Línea de continuación → añadir a descripción si no son números
                    for w in line_words:
                        if not _CURRENCY_RE.match(w["text"]):
                            cur_row.desc_parts.append(w["text"])

            if cur_row is not None:
                rows.append(cur_row)

    # Convertir rows a movements con saldo acumulado
    saldo_running = saldo_inicial
    for row in rows:
        fecha = _parse_bbva_date(row.oper_date, anio, mes_fin)
        if fecha is None:
            continue

        cargo = row.cargo
        abono = row.abono

        # Saldo: usar liq_saldo > oper_saldo > calculado
        if row.liq_saldo is not None:
            saldo = row.liq_saldo
        elif row.oper_saldo is not None:
            saldo = row.oper_saldo
        else:
            saldo = saldo_running + abono - cargo

        saldo_running = saldo

        descripcion = " ".join(row.desc_parts).strip()

        movimientos.append(
            Movement(
                fecha=fecha,
                descripcion=descripcion,
                abono=abono,
                cargo=cargo,
                saldo=saldo,
                banco=BankId.BBVA,
                cuenta=cuenta,
                archivo_origen=archivo_origen,
            )
        )

    return movimientos
