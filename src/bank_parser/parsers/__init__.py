"""Registry de parsers por banco.

Cada parser hereda de bank_parser.parsers.base.BankParser y se registra
aqui con su BankId. Agregar un banco nuevo es una sola linea adicional
en BANK_REGISTRY.

Uso desde el pipeline:

    parser_cls = BANK_REGISTRY[bank_id]
    parser = parser_cls()
    statement = parser.parse(text, archivo_origen=name)
"""

from __future__ import annotations

from bank_parser.core.schema import BankId
from bank_parser.parsers.banamex import BanamexParser
from bank_parser.parsers.base import BankParser

BANK_REGISTRY: dict[BankId, type[BankParser]] = {
    BankId.BANAMEX: BanamexParser,
    # Fase 2: registrar BBVA, BanBajio, Banregio, Banorte aqui.
}


def get_parser(bank_id: BankId) -> BankParser:
    """Instancia el parser registrado para bank_id."""
    return BANK_REGISTRY[bank_id]()
