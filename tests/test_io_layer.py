"""Tests para io_layer: lectura de PDFs directos y extracción de ZIPs."""

from __future__ import annotations

from pathlib import Path

import pytest

from bank_parser.core.exceptions import UnsupportedFileError
from bank_parser.core.io_layer import ExtractedPdf, extract_pdfs_from_input, read_pdf_text


def test_extract_pdf_directo(samples_dir: Path) -> None:
    pdf_path = samples_dir / "banamex" / "banamex_micuenta_abr2026.pdf"
    if not pdf_path.exists():
        pytest.skip("PDF de muestra no disponible")
    result = extract_pdfs_from_input(pdf_path)
    assert len(result) == 1
    assert isinstance(result[0], ExtractedPdf)
    assert result[0].nombre == "banamex_micuenta_abr2026.pdf"
    assert result[0].origen == pdf_path
    assert len(result[0].contenido) > 0


def test_extract_zip_banorte(samples_dir: Path) -> None:
    zip_path = samples_dir / "banorte" / "banorte_celomex_ene2026.zip"
    if not zip_path.exists():
        pytest.skip("Muestra no disponible")
    result = extract_pdfs_from_input(zip_path)
    assert len(result) >= 1
    assert all(isinstance(r, ExtractedPdf) for r in result)
    assert all(r.contenido for r in result)
    assert all("banorte_celomex_ene2026.zip" in r.nombre for r in result)


def test_extract_zip_banbajio(samples_dir: Path) -> None:
    zip_path = samples_dir / "banbajio" / "banbajio_celomex_feb2026.zip"
    if not zip_path.exists():
        pytest.skip("Muestra no disponible")
    result = extract_pdfs_from_input(zip_path)
    assert len(result) >= 1


def test_unsupported_extension(tmp_path: Path) -> None:
    f = tmp_path / "archivo.txt"
    f.write_text("hola")
    with pytest.raises(UnsupportedFileError, match="no soportado"):
        extract_pdfs_from_input(f)


def test_archivo_no_existe(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedFileError, match="No existe"):
        extract_pdfs_from_input(tmp_path / "noexiste.pdf")


def test_read_pdf_text_banamex(samples_dir: Path) -> None:
    pdf_path = samples_dir / "banamex" / "banamex_micuenta_abr2026.pdf"
    if not pdf_path.exists():
        pytest.skip("PDF de muestra no disponible")
    pdf_bytes = pdf_path.read_bytes()
    text = read_pdf_text(pdf_bytes)
    assert "MiCuenta" in text
    assert "SALDO" in text
    assert len(text) > 500
