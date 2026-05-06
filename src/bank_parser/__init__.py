"""bank_parser — Parser de estados de cuenta bancarios mexicanos.

API pública de alto nivel::

    from bank_parser import parse_pdf, BankId, Statement

Uso rápido::

    statements = parse_pdf("estado.pdf")      # list[Statement]
    for mov in statements[0].movements:
        print(mov.fecha, mov.descripcion, mov.abono, mov.cargo)

Para detalles de arquitectura ver ``docs/architecture.md``.
"""

from __future__ import annotations

from pathlib import Path

from bank_parser._version import __version__
from bank_parser.core.schema import BankId, Movement, Statement, StatementSummary


def parse_pdf(path: str | Path) -> list[Statement]:
    """Procesa un PDF (o ZIP con PDFs) y devuelve los Statements parseados.

    Atajo de alto nivel sobre :func:`bank_parser.core.pipeline.process_file`.
    Útil para uso programático sin importar el pipeline directamente.

    Args:
        path: Ruta al PDF o ZIP.

    Returns:
        Lista de :class:`Statement` (uno por PDF procesado).

    Raises:
        :class:`~bank_parser.core.exceptions.BankParserError`: cualquier
        error de detección, parseo o validación.
    """
    from bank_parser.core.pipeline import process_file

    return process_file(Path(path))


__all__ = [
    "BankId",
    "Movement",
    "Statement",
    "StatementSummary",
    "__version__",
    "parse_pdf",
]
