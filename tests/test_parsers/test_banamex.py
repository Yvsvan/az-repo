"""Tests del parser de Banamex.

Estrategia: regression test contra el sample real más golden file.
Si el parser cambia legítimamente, regenerar con::

    pytest tests/test_parsers/test_banamex.py --regen-golden
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bank_parser.core.io_layer import read_pdf_text
from bank_parser.core.schema import BankId, Statement
from bank_parser.parsers.banamex import BanamexParser
from bank_parser.validators.balance import validar_cuadre

SAMPLE = "banamex/banamex_micuenta_abr2026.pdf"
GOLDEN = "banamex/banamex_micuenta_abr2026.json"


@pytest.fixture(scope="module")
def statement(samples_dir: Path) -> Statement:
    pdf_path = samples_dir / SAMPLE
    text = read_pdf_text(pdf_path.read_bytes())
    parser = BanamexParser()
    return parser.parse(text, archivo_origen=pdf_path.name)


def test_banco_es_banamex(statement: Statement) -> None:
    assert statement.summary.banco == BankId.BANAMEX


def test_titular_extraido(statement: Statement) -> None:
    assert "AGUILERA" in statement.summary.titular.upper()


def test_rfc_extraido(statement: Statement) -> None:
    assert statement.summary.rfc == "AUAI000504PN6"


def test_movimientos_no_vacios(statement: Statement) -> None:
    assert len(statement.movements) > 0


def test_cuadre(statement: Statement) -> None:
    """El parser debe producir totales que cuadren con el resumen del PDF."""
    warnings = validar_cuadre(statement)
    assert warnings == [], f"warnings inesperados: {warnings}"


def test_golden(statement: Statement, samples_dir: Path, regen_golden: bool) -> None:
    """Regression test: el parser produce exactamente el Statement esperado."""
    golden_path = samples_dir / "golden" / GOLDEN.split("/", 1)[1].replace(".pdf", ".json")
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
