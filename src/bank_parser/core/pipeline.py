"""Pipeline de procesamiento end-to-end.

Conecta los módulos:

    PDF/ZIP path → io_layer → bank_detector → parser → validator → Statement

Una sola función pública: :func:`process_file`. Devuelve uno o más
``Statement`` (uno por PDF dentro de un ZIP).

Esta capa no escribe a disco ni habla con la GUI: sólo devuelve datos.
Los exporters y la GUI son responsables de la presentación.
"""

from __future__ import annotations

from pathlib import Path

from bank_parser.core.bank_detector import detect_bank
from bank_parser.core.io_layer import extract_pdfs_from_input, read_pdf_text
from bank_parser.core.schema import Statement
from bank_parser.parsers import get_parser
from bank_parser.validators.balance import validar_cuadre


def process_file(path: Path) -> list[Statement]:
    """Procesa un PDF (o ZIP con PDFs) y devuelve los Statements parseados.

    No relanza errores de validación: los pone en ``Statement.warnings``
    para que el caller decida si exportar o no.

    Lanza :class:`UnsupportedFileError`, :class:`BankDetectionError`,
    :class:`FormatChangedError` y :class:`ParseError` cuando el PDF
    no se puede procesar (la GUI los captura por separado).
    """
    pdfs = extract_pdfs_from_input(path)
    statements: list[Statement] = []
    for pdf in pdfs:
        text = read_pdf_text(pdf.contenido)
        bank_id = detect_bank(text)
        parser = get_parser(bank_id)
        statement = parser.parse(text, archivo_origen=pdf.nombre)
        # Adjuntamos warnings de cuadre.
        warnings = validar_cuadre(statement)
        if warnings:
            statement = statement.model_copy(
                update={"warnings": list(statement.warnings) + warnings}
            )
        statements.append(statement)
    return statements
