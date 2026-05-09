"""Tests del parser de Banorte (Enlace Negocios).

Regenerar golden::

    pytest tests/test_parsers/test_banorte.py --regen-golden
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bank_parser.core.io_layer import extract_pdfs_from_input, read_pdf_text
from bank_parser.core.schema import BankId, Statement
from bank_parser.parsers.banorte import BanorteParser
from bank_parser.validators.balance import validar_cuadre

SAMPLE = "banorte/banorte_celomex_ene2026.zip"
GOLDEN = "banorte_celomex_ene2026.json"


@pytest.fixture(scope="module")
def statement(samples_dir: Path) -> Statement:
    sample_path = samples_dir / SAMPLE
    if not sample_path.exists():
        pytest.skip(f"Muestra no disponible: {sample_path.name}")
    pdfs = extract_pdfs_from_input(sample_path)
    text = read_pdf_text(pdfs[0].contenido)
    parser = BanorteParser()
    return parser.parse(text, pdf_bytes=pdfs[0].contenido, archivo_origen=pdfs[0].nombre)


def test_banco_es_banorte(statement: Statement) -> None:
    assert statement.summary.banco == BankId.BANORTE


def test_rfc_extraido(statement: Statement) -> None:
    assert statement.summary.rfc == "CEL810729LY8"


def test_cuenta_extraida(statement: Statement) -> None:
    assert "0660792468" in statement.summary.cuenta


def test_periodo(statement: Statement) -> None:
    s = statement.summary
    assert s.periodo_inicio.year == 2026
    assert s.periodo_inicio.month == 1
    assert s.periodo_fin.month == 1


def test_movimientos_no_vacios(statement: Statement) -> None:
    assert len(statement.movements) > 0


def test_cuadre(statement: Statement) -> None:
    warnings = validar_cuadre(statement)
    assert warnings == [], f"warnings inesperados: {warnings}"


def test_golden(statement: Statement, samples_dir: Path, regen_golden: bool) -> None:
    golden_path = samples_dir / "golden" / GOLDEN
    actual_json = json.loads(statement.model_dump_json())

    if regen_golden or not golden_path.exists():
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(json.dumps(actual_json, indent=2, ensure_ascii=False, default=str))
        pytest.skip(f"Golden regenerado en {golden_path}.")

    expected = json.loads(golden_path.read_text())
    assert actual_json == expected, (
        f"El Statement difiere del golden ({golden_path}). "
        "Si el cambio es legítimo, regenera con --regen-golden."
    )
