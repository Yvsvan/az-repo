"""Parser para estados de cuenta de Banamex (Citibanamex / MiCuenta).

Estructura del PDF (resumen):

* Encabezado de tabla: ``FECHA CONCEPTO RETIROS DEPÓSITOS SALDO``.
* Fechas en formato ``DD MMM`` con mes en español abreviado en
  mayúsculas (``17 MAR``, ``01 ABR``).
* Cada movimiento ocupa N líneas: la primera empieza con la fecha y
  abre la descripción; las intermedias son detalle (``CAJA``, ``AUT``,
  ``HORA``, ``RASTREO``); la **última** termina con el monto y el
  saldo, o sólo el saldo si el movimiento es de $0 (exenciones).
* Si el monto no aparece explícito, se infiere por delta del saldo.
* Las páginas tienen un encabezado/footer que se filtra.
* La cuenta principal es ``MiCuenta``. Si el PDF también incluye la
  sección ``AHORRO FACIL``, este parser la ignora (es una cuenta
  separada, debería procesarse aparte si el cliente la usa).
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
# Patrones (compilados una vez)
# ---------------------------------------------------------------------------

# "Período del 13 de marzo al 12 de abril del 2026"
_PERIODO_RE = re.compile(
    r"Período\s+del\s+(\d{1,2})\s+de\s+([A-Za-zñÑáéíóúÁÉÍÓÚ]+)"
    r"\s+al\s+(\d{1,2})\s+de\s+([A-Za-zñÑáéíóúÁÉÍÓÚ]+)\s+del\s+(\d{4})",
    re.IGNORECASE,
)

# "Saldo al Corte 53,745.16"  (en el resumen)
_SALDO_AL_CORTE_RE = re.compile(r"Saldo\s+al\s+Corte\s+([\d,]+\.\d{2})", re.IGNORECASE)

# "(+) 8 Depósitos 91,097.06"
_TOTAL_DEPOSITOS_RE = re.compile(r"\(\+\)\s+\d*\s*Depósitos\s+([\d,]+\.\d{2})")

# "(-) 7 Retiros/Otros cargos 41,088.25"
_TOTAL_RETIROS_RE = re.compile(r"\(-\)\s+\d*\s*Retiros[/\w\s]*\s+([\d,]+\.\d{2})")

# "Saldo anterior En pesos M.N. 3,736.35"
_SALDO_ANTERIOR_RESUMEN_RE = re.compile(
    r"Saldo\s+anterior\s+En\s+pesos\s+M\.N\.\s+([\d,]+\.\d{2})", re.IGNORECASE
)

# "Número de cuenta de cheques 70138905215"
_CUENTA_PATTERNS = [
    r"Número\s+de\s+cuenta\s+de\s+cheques\s+(\d+)",
    r"Número\s+de\s+contrato\s+(\d+)",
]

# Marcador que abre el detalle de movimientos.
_DETALLE_HEADER = "FECHA CONCEPTO RETIROS DEPÓSITOS SALDO"

# Lineas a filtrar dentro de la sección de movimientos (ruido de page break).
_NOISE_PATTERNS = [
    re.compile(r"^Página\s+\d+\s+de\s+\d+\s+\d+\s*$"),
    re.compile(r"^FECHA\s+CONCEPTO\s+RETIROS\s+DEPÓSITOS\s+SALDO\s*$"),
    re.compile(r"^Detalle\s+de\s+Operaciones"),
    re.compile(r"^Centro\s+de\s+Atención"),
    re.compile(r"^Ciudad\s+de\s+México:"),
    re.compile(r"^Resto\s+del\s+país:"),
    re.compile(r"^MiCuenta\s*$"),
    re.compile(r"^Resumen\s+del\s+\d"),
    re.compile(r"^Número\s+de\s+contrato\s+\d"),
]

# Línea que empieza un movimiento: "DD MMM ..."
_MOV_DATE_RE = re.compile(r"^(\d{2})\s+([A-Z]{3})\s+", re.MULTILINE)

# Currency en formato mexicano: 1,234.56 o 1234.56  (sin $ ni espacios delante).
_CURRENCY_RE = re.compile(r"\b\d{1,3}(?:,\d{3})*\.\d{2}\b")


class BanamexParser(BankParser):
    """Parser para estados de cuenta Banamex MiCuenta."""

    bank_id = BankId.BANAMEX

    expected_markers: tuple[str, ...] = (
        "MiCuenta",
        _DETALLE_HEADER,
        "Saldo al Corte",
        "Saldo anterior",
    )

    def parse(
        self,
        pdf_text: str,
        *,
        pdf_bytes: bytes | None = None,
        archivo_origen: str,
    ) -> Statement:
        # --- Capa 1: validación estructural -----------------------------------
        for marker in self.expected_markers:
            if marker not in pdf_text:
                raise FormatChangedError("Banamex", marker)

        # --- Metadatos del periodo --------------------------------------------
        periodo = _PERIODO_RE.search(pdf_text)
        if not periodo:
            raise FormatChangedError(
                "Banamex",
                "Período del DD de MES al DD de MES del AAAA",
                hint="No se pudo determinar el periodo del estado de cuenta.",
            )
        d_ini, mes_ini_str, d_fin, mes_fin_str, year_str = periodo.groups()
        anio_fin = int(year_str)
        mes_ini = MES_ES_LARGO[mes_ini_str.upper()]
        mes_fin = MES_ES_LARGO[mes_fin_str.upper()]
        anio_ini = anio_fin - 1 if mes_fin < mes_ini else anio_fin
        periodo_inicio = date(anio_ini, mes_ini, int(d_ini))
        periodo_fin = date(anio_fin, mes_fin, int(d_fin))

        # --- Saldos y totales del resumen -------------------------------------
        m_saldo_anterior = _SALDO_ANTERIOR_RESUMEN_RE.search(pdf_text)
        if not m_saldo_anterior:
            raise FormatChangedError("Banamex", "Saldo anterior En pesos M.N. <monto>")
        saldo_inicial = limpiar_numero(m_saldo_anterior.group(1))

        m_saldo_corte = _SALDO_AL_CORTE_RE.search(pdf_text)
        saldo_final = limpiar_numero(m_saldo_corte.group(1)) if m_saldo_corte else Decimal("0")

        m_dep = _TOTAL_DEPOSITOS_RE.search(pdf_text)
        total_abonos = limpiar_numero(m_dep.group(1)) if m_dep else Decimal("0")

        m_ret = _TOTAL_RETIROS_RE.search(pdf_text)
        total_cargos = limpiar_numero(m_ret.group(1)) if m_ret else Decimal("0")

        # --- Datos del titular ------------------------------------------------
        titular = _extract_titular(pdf_text)
        rfc = extract_rfc(pdf_text)
        cuenta = extract_first_match(_CUENTA_PATTERNS, pdf_text) or ""

        # --- Movimientos ------------------------------------------------------
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
            banco=BankId.BANAMEX,
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
    """Heurística: el titular aparece en mayúsculas justo arriba de la dirección."""
    # Buscamos un nombre todo-mayúsculas (con espacios) seguido de una calle.
    m = re.search(
        r"(?m)^([A-ZÑÁÉÍÓÚ][A-ZÑÁÉÍÓÚ\s]{8,60})\s*\nC\s+[A-ZÑÁÉÍÓÚ]",
        text,
    )
    if m:
        return m.group(1).strip()
    # Fallback: regresar cadena vacía si no encontramos nada.
    return ""


def _strip_noise(text: str) -> str:
    """Quita líneas que son artefactos de paginación (footers / encabezados repetidos)."""
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
    """Aísla la sección de movimientos: desde el primer header de tabla hasta
    que empieza la sección de AHORRO FACIL (otra cuenta dentro del mismo PDF).
    """
    start = text.find(_DETALLE_HEADER)
    if start < 0:
        raise FormatChangedError("Banamex", _DETALLE_HEADER)
    body = text[start + len(_DETALLE_HEADER) :]

    # Cortar al inicio de AHORRO FACIL si existe.
    end_markers = [
        "AHORRO FACIL",
        "Saldo Final",
    ]
    for marker in end_markers:
        idx = body.find(marker)
        if idx >= 0:
            body = body[:idx]
            break
    return body


def _split_by_date(text: str) -> list[str]:
    """Devuelve bloques de movimiento, uno por fecha encontrada al inicio de línea."""
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
    """Extrae (monto, saldo) del bloque.

    Reglas:

    * El **saldo** es el último número de moneda que aparece en el bloque
      pegado al final de una línea (por convención del layout).
    * El **monto** es el penúltimo número en esa misma línea final, si existe.
    * Si la última línea sólo tiene un número, monto = ``None`` (se infiere
      por delta del saldo).

    Lanza :class:`ParseError` si no se encuentra ningún número.
    """
    # Iteramos las líneas en reversa hasta encontrar una con números al final.
    for line in reversed(block.splitlines()):
        nums = _CURRENCY_RE.findall(line)
        if not nums:
            continue
        # Verificamos que el último número esté efectivamente al final de la línea
        # (sin texto siguiente). Si no, no es la línea de cierre del movimiento.
        if not line.rstrip().endswith(nums[-1]):
            continue
        if len(nums) >= 2:
            return limpiar_numero(nums[-2]), limpiar_numero(nums[-1])
        return None, limpiar_numero(nums[-1])
    raise ParseError(f"Bloque sin números detectables: {block[:80]!r}")


def _build_descripcion(block: str, monto_str_to_strip: str | None, saldo_str_to_strip: str) -> str:
    """Junta las líneas de descripción quitando los números finales y la fecha."""
    lines = block.splitlines()
    if not lines:
        return ""
    # Quitar la fecha de la primera línea ("17 MAR ").
    lines[0] = re.sub(r"^\d{2}\s+[A-Z]{3}\s+", "", lines[0])
    # En la última línea, quitar el(los) número(s) finales.
    last = lines[-1].rstrip()
    if monto_str_to_strip and last.endswith(saldo_str_to_strip):
        # Quitar saldo y luego (si está) el monto.
        last = last[: -len(saldo_str_to_strip)].rstrip()
        if last.endswith(monto_str_to_strip):
            last = last[: -len(monto_str_to_strip)].rstrip()
    elif last.endswith(saldo_str_to_strip):
        last = last[: -len(saldo_str_to_strip)].rstrip()
    lines[-1] = last
    # Concatenar y normalizar espacios.
    desc = " ".join(line.strip() for line in lines if line.strip())
    return desc


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
        # Fecha
        m_fecha = _MOV_DATE_RE.match(bloque)
        if not m_fecha:
            continue
        dia = int(m_fecha.group(1))
        mes_str = m_fecha.group(2)
        mes = MES_ES_ABREV.get(mes_str)
        if mes is None:
            continue

        # Si el movimiento es "SALDO ANTERIOR" lo saltamos (no es transacción).
        primer_linea = bloque.splitlines()[0]
        if "SALDO ANTERIOR" in primer_linea.upper():
            saldo_prev = saldo_inicial
            continue

        # Año: si el mes coincide con el de inicio del periodo y es distinto al
        # mes de fin, usamos el año de inicio; si no, el de fin.
        anio = anio_ini if (mes == mes_ini and mes != mes_fin) else anio_fin
        if mes == mes_ini and mes == mes_fin:
            anio = anio_fin  # periodo dentro de un solo mes → año de fin

        try:
            fecha = date(anio, mes, dia)
        except ValueError:
            # Día inválido → saltamos sin romper el parser.
            continue

        # Monto y saldo.
        try:
            monto_explicito, saldo = _last_amounts_in_block(bloque)
        except ParseError:
            continue

        # Determinar abono/cargo por delta de saldo.
        delta = saldo - saldo_prev
        if delta > 0:
            abono = delta
            cargo = Decimal("0")
        elif delta < 0:
            abono = Decimal("0")
            cargo = -delta
        else:
            # Saldo no cambió → movimiento de $0 (exención, ajuste).
            abono = Decimal("0")
            cargo = Decimal("0")

        # Descripción limpia (sin la fecha ni los números finales).
        # Para reconstruir las cadenas tal como aparecen en el PDF:
        #   - el saldo siempre tiene formato con coma, pero monto puede no.
        # Lo más simple: encontrar las representaciones literales en el bloque.
        saldo_str_lit = _find_literal_for(bloque, saldo)
        monto_str_lit = (
            _find_literal_for(bloque, monto_explicito) if monto_explicito is not None else None
        )
        descripcion = _build_descripcion(
            bloque,
            monto_str_to_strip=monto_str_lit,
            saldo_str_to_strip=saldo_str_lit,
        )

        movimientos.append(
            Movement(
                fecha=fecha,
                descripcion=descripcion,
                abono=abono,
                cargo=cargo,
                saldo=saldo,
                banco=BankId.BANAMEX,
                cuenta=cuenta,
                archivo_origen=archivo_origen,
            )
        )
        saldo_prev = saldo

    return movimientos


def _find_literal_for(block: str, value: Decimal) -> str:
    """Busca la representación literal de ``value`` (con o sin coma) en el bloque."""
    formatted_with_comma = f"{value:,.2f}"
    if formatted_with_comma in block:
        return formatted_with_comma
    formatted_no_comma = f"{value:.2f}"
    if formatted_no_comma in block:
        return formatted_no_comma
    return formatted_with_comma  # fallback razonable
