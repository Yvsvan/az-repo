"""Tests de integración end-to-end del pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from bank_parser.core.pipeline import process_file
from bank_parser.core.schema import BankId


def test_pipeline_banamex(samples_dir: Path) -> None:
    pdf_path = samples_dir / "banamex" / "banamex_micuenta_abr2026.pdf"
    if not pdf_path.exists():
        pytest.skip("PDF de muestra no disponible")
    statements = process_file(pdf_path)
    assert len(statements) == 1
    s = statements[0]
    assert s.summary.banco == BankId.BANAMEX
    assert len(s.movements) > 0
    assert s.warnings == []


def test_pipeline_zip_banorte(samples_dir: Path) -> None:
    zip_path = samples_dir / "banorte" / "banorte_celomex_ene2026.zip"
    if not zip_path.exists():
        pytest.skip("Muestra no disponible")
    statements = process_file(zip_path)
    assert len(statements) >= 1
    assert statements[0].summary.banco == BankId.BANORTE
    assert len(statements[0].movements) > 0
