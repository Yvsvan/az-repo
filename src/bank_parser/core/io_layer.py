"""Capa de I/O: leer PDFs (directos o dentro de ZIPs).

Esta capa es la única que toca disco. Cualquier otro módulo recibe
texto o un objeto ``pdfplumber.PDF`` ya abierto.

Funciones públicas:

* :func:`extract_pdfs_from_input` — recibe un path a PDF o ZIP y devuelve
  una lista de ``ExtractedPdf`` (con bytes en memoria, listos para parsear).
* :func:`read_pdf_text` — convierte un PDF en texto plano concatenado.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pdfplumber

from bank_parser.core.exceptions import UnsupportedFileError


@dataclass(frozen=True)
class ExtractedPdf:
    """Un PDF listo para parsear, con su nombre lógico de origen."""

    nombre: str           # nombre visible (p. ej. "edo_feb.pdf" o "zip/edo.pdf")
    contenido: bytes      # bytes del PDF
    origen: Path          # archivo de origen (PDF o ZIP)


def extract_pdfs_from_input(path: Path) -> list[ExtractedPdf]:
    """Devuelve una lista de PDFs a partir de un path a PDF o ZIP.

    Si el path es un PDF, devuelve una lista de un solo elemento.
    Si es un ZIP, extrae todos los PDFs adentro (recursivamente).

    Lanza :class:`UnsupportedFileError` si el archivo no es ni PDF ni ZIP.
    """
    if not path.exists():
        raise UnsupportedFileError(f"No existe el archivo: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return [ExtractedPdf(nombre=path.name, contenido=path.read_bytes(), origen=path)]
    if suffix == ".zip":
        return _extract_pdfs_from_zip(path)
    raise UnsupportedFileError(
        f"Tipo de archivo no soportado: '{suffix}'. Solo se aceptan .pdf y .zip."
    )


def _extract_pdfs_from_zip(zip_path: Path) -> list[ExtractedPdf]:
    """Extrae todos los .pdf de un ZIP en memoria (no toca el filesystem)."""
    out: list[ExtractedPdf] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if not info.filename.lower().endswith(".pdf"):
                continue
            data = zf.read(info)
            out.append(
                ExtractedPdf(
                    nombre=f"{zip_path.name}::{info.filename}",
                    contenido=data,
                    origen=zip_path,
                )
            )
    if not out:
        raise UnsupportedFileError(
            f"El ZIP {zip_path.name} no contiene PDFs."
        )
    return out


def read_pdf_text(pdf_bytes: bytes) -> str:
    """Convierte bytes de un PDF en su texto plano concatenado.

    Une el texto de todas las páginas con saltos de línea. Si el PDF
    está escaneado (sin capa de texto), devuelve cadena vacía y el
    parser de banco detectará la situación con su validación de
    fingerprints.
    """
    texto_paginas: list[str] = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            texto_paginas.append(page.extract_text() or "")
    return "\n".join(texto_paginas)


def open_pdf(pdf_bytes: bytes) -> pdfplumber.PDF:
    """Abre un PDF desde bytes. El caller es responsable de cerrarlo.

    Útil para parsers que necesitan acceso a tablas o coordenadas
    (BBVA usa ``extract_tables``).
    """
    return pdfplumber.open(BytesIO(pdf_bytes))
