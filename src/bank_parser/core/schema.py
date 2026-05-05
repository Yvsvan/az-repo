"""Modelos de datos centrales (pydantic).

Todo el pipeline gira en torno a tres modelos:

* :class:`Movement` — un renglón de la tabla del estado de cuenta.
* :class:`StatementSummary` — metadatos del estado de cuenta (titular,
  RFC, periodo, totales).
* :class:`Statement` — la unión de los dos: lo que produce un parser
  y lo que consumen los exporters.

Todos los importes son :class:`decimal.Decimal` para evitar errores de
redondeo binario en operaciones financieras.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class BankId(str, Enum):
    """Identificador canónico de un banco soportado."""

    BANAMEX = "banamex"
    BBVA = "bbva"
    BANBAJIO = "banbajio"
    BANREGIO = "banregio"
    BANORTE = "banorte"

    @property
    def display_name(self) -> str:
        """Nombre legible del banco para mostrar en UI / logs."""
        return {
            BankId.BANAMEX: "Banamex",
            BankId.BBVA: "BBVA",
            BankId.BANBAJIO: "BanBajío",
            BankId.BANREGIO: "Banregio",
            BankId.BANORTE: "Banorte",
        }[self]


class Movement(BaseModel):
    """Un renglón de la tabla de movimientos.

    Convenciones:

    * ``abono`` y ``cargo`` son siempre positivos. El movimiento es
      un cargo si ``cargo > 0``, abono si ``abono > 0``. Nunca ambos.
    * ``saldo`` es el saldo después de aplicar este movimiento.
    """

    model_config = ConfigDict(frozen=True)

    fecha: date
    descripcion: str
    abono: Decimal = Decimal("0")
    cargo: Decimal = Decimal("0")
    saldo: Decimal
    banco: BankId
    cuenta: str
    archivo_origen: str

    @property
    def es_abono(self) -> bool:
        return self.abono > 0


class StatementSummary(BaseModel):
    """Metadatos del estado de cuenta (encabezado y resumen)."""

    model_config = ConfigDict(frozen=True)

    banco: BankId
    titular: str
    rfc: str | None = None
    cuenta: str
    periodo_inicio: date | None = None
    periodo_fin: date | None = None
    saldo_inicial: Decimal
    saldo_final: Decimal
    total_abonos: Decimal
    total_cargos: Decimal
    archivo_origen: str


class Statement(BaseModel):
    """Salida completa del parser para un PDF."""

    model_config = ConfigDict(frozen=True)

    summary: StatementSummary
    movements: list[Movement]
    warnings: list[str] = Field(default_factory=list)
