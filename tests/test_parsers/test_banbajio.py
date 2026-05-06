"""Tests del parser de BanBajío (Cuenta Conecta).

Regenerar golden::

    pytest tests/test_parsers/test_banbajio.py --regen-golden
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bank_parser.core.io_layer import read_pdf_text
from bank_parser.core.schema import BankId, Statement
from bank_parser.parsers.banbajio import BanBajioParser
from bank_parser.validators.balance import validar_cuadre

SAMPLE = "banbajio/banbajio_gaba_1154_feb2026.pdf"
GOLDEN = "banbajio_gaba_1154_feb2026.json"


@pytest.fixture(scope="module")
def statement(samples_dir: Path) -> Statement:
    pdf_path = samples_dir / SAMPLE
    text = read_pdf_text(pdf_path.read_bytes())
    parser = BanBajioParser()
    return parser.parse(text, pdf_bytes=pdf_path.read_bytes(), archivo_origen=pdf_path.name)


def test_banco_es_banbajio(statement: Statement) -> None:
    assert statement.summary.banco == BankId.BANBAJIO


def test_rfc_extraido(statement: Statement) -> None:
    assert statement.summary.rfc == "GABA880703B17"


def test_cuenta_extraida(statement: Statement) -> None:
    assert statement.summary.cuenta != ""


def test_periodo(statement: Statement) -> None:
    s = statement.summary
    assert s.periodo_inicio.year == 2026
    assert s.periodo_inicio.month == 2
    assert s.periodo_fin.month == 2


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
