"""Smoke tests: imports y API pública del paquete."""

from pathlib import Path

import pytest

import bank_parser


def test_package_imports() -> None:
    assert bank_parser.__version__


def test_version_is_semver() -> None:
    parts = bank_parser.__version__.split(".")
    assert len(parts) == 3, f"versión no es semver: {bank_parser.__version__}"
    for p in parts:
        # Permite suffixes alpha/beta/rc en el patch.
        head = p.split("-")[0]
        assert head.isdigit(), f"componente no numérico: {p}"


def test_public_api_exports() -> None:
    """Todos los símbolos públicos declarados en __all__ son importables."""
    for name in bank_parser.__all__:
        assert hasattr(bank_parser, name), f"'{name}' declarado en __all__ pero no existe"


def test_parse_pdf_convenience(samples_dir: Path) -> None:
    """parse_pdf es un atajo funcional sobre process_file."""
    pdf = samples_dir / "banamex" / "banamex_micuenta_abr2026.pdf"
    if not pdf.exists():
        pytest.skip("PDF de muestra no disponible")
    statements = bank_parser.parse_pdf(pdf)
    assert len(statements) == 1
    assert statements[0].summary.banco == bank_parser.BankId.BANAMEX
    assert len(statements[0].movements) > 0
