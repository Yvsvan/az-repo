"""Jerarquía de excepciones del paquete.

Reglas:

* Toda excepción que pueda llegar a la GUI hereda de :class:`BankParserError`,
  para que la GUI tenga un solo punto de captura y sepa que el mensaje
  es seguro de mostrar al usuario (texto en español, contexto incluido).
* Las excepciones de bajo nivel (IO, parsing) **no** se filtran a la GUI:
  el pipeline las traduce a la jerarquía pública.
"""

from __future__ import annotations


class BankParserError(Exception):
    """Excepción base de cualquier error originado por bank_parser."""


class UnsupportedFileError(BankParserError):
    """El archivo no es un PDF/ZIP soportado."""


class BankDetectionError(BankParserError):
    """No se pudo identificar al banco emisor con suficiente confianza.

    Contiene la lista de bancos candidatos (si hubo más de uno) o vacía
    si ninguno coincidió.
    """

    def __init__(self, message: str, candidates: list[str] | None = None) -> None:
        super().__init__(message)
        self.candidates = candidates or []


class FormatChangedError(BankParserError):
    """El PDF tiene fingerprints del banco pero el layout cambió.

    Se lanza cuando un parser identifica al banco correcto pero no
    encuentra los marcadores estructurales esperados (encabezados de
    tabla, etiquetas de saldo). Indica que el banco actualizó su
    plantilla y el parser necesita actualizarse.
    """

    def __init__(self, bank: str, missing_marker: str, *, hint: str = "") -> None:
        msg = (
            f"El formato de {bank} cambió: no se encontró el marcador "
            f"esperado '{missing_marker}'."
        )
        if hint:
            msg += f" {hint}"
        msg += " Reporta este PDF al equipo de desarrollo."
        super().__init__(msg)
        self.bank = bank
        self.missing_marker = missing_marker


class ParseError(BankParserError):
    """Error genérico al parsear el PDF (regex no matcheó, fila malformada)."""


class ValidationFailedError(BankParserError):
    """El cuadre numérico (saldo_inicial + abonos - cargos = saldo_final) falló."""

    def __init__(self, expected: object, actual: object, diff: object) -> None:
        super().__init__(
            f"Cuadre falló: esperado {expected}, calculado {actual}, diferencia {diff}."
        )
        self.expected = expected
        self.actual = actual
        self.diff = diff
