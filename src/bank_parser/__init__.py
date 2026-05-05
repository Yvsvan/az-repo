"""bank_parser — Parser de estados de cuenta bancarios mexicanos.

API pública del paquete::

    from bank_parser import parse_pdf, BankId, Statement

Para uso programático rápido::

    statement = parse_pdf("estado.pdf")
    for mov in statement.movements:
        print(mov.fecha, mov.descripcion, mov.abono, mov.cargo)

Para detalles de arquitectura ver ``docs/architecture.md``.
"""

from bank_parser._version import __version__

__all__ = ["__version__"]
