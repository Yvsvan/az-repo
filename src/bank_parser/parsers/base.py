"""Interfaz abstracta para todos los parsers de banco.

Cada banco implementa una subclase y se registra en
``parsers/__init__.py::BANK_REGISTRY``. La GUI y la CLI consumen
exclusivamente esta interfaz, lo que mantiene a los parsers
desacoplados del resto del sistema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from bank_parser.core.schema import BankId, Statement


class BankParser(ABC):
    """Contrato que todo parser de banco debe cumplir."""

    #: Identificador único del banco. Las subclases deben sobrescribirlo.
    bank_id: BankId

    #: Substrings que deben aparecer en el texto del PDF para considerar
    #: que el formato no cambió. Se valida al inicio de :meth:`parse`.
    expected_markers: tuple[str, ...] = ()

    @abstractmethod
    def parse(
        self,
        pdf_text: str,
        *,
        pdf_bytes: bytes | None = None,
        archivo_origen: str,
    ) -> Statement:
        """Convierte texto plano de un PDF en un :class:`Statement`.

        :param pdf_text: texto extraído de todas las páginas.
        :param pdf_bytes: bytes crudos del PDF (necesario para parsers que
            usan posicionamiento de palabras, p. ej. BBVA).
        :param archivo_origen: nombre del archivo (para trazabilidad).
        """
        raise NotImplementedError
