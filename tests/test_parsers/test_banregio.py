"""Tests del parser de Banregio (Cuenta Naranja Negocios).

Nota: Banregio incluye 440.80 en cargos del resumen que no están listados
como movimientos individuales en la tabla (comisiones cobradas fuera del
detalle). El cuadre de movimientos vs resumen producirá warnings; esto es
comportamiento esperado y se verifica explícitamente.

Regenerar golden::

    pytest tests/test_parsers/test_banregio.py --regen-golden
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bank_parser.core.io_layer import read_pdf_text
from bank_parser.core.schema import BankId, Statement
from bank_parser.parsers.banregio import BanregioParser
from bank_parser.validators.balance import validar_cuadre

SAMPLE = "banregio/banregio_celomex_ene2026.pdf"
GOLDEN = "banregio_celomex_ene2026.json"

# Banregio cobra comisiones fuera del detalle de movimientos; el total PDF
# incluye 440.80 que no aparece como línea individual.
_EXPECTED_CARGO_DIFF = "440.80"


@pytest.fixture(scope="module")
def statement(samples_dir: Path) -> Statement:
    pdf_path = samples_dir / SAMPLE
    if not pdf_path.exists():
        pytest.skip(f"PDF de muestra no disponible: {pdf_path.name}")
    text = read_pdf_text(pdf_path.read_bytes())
    parser = BanregioParser()
    return parser.parse(text, pdf_bytes=pdf_path.read_bytes(), archivo_origen=pdf_path.name)


def test_banco_es_banregio(statement: Statement) -> None:
    assert statement.summary.banco == BankId.BANREGIO


def test_rfc_extraido(statement: Statement) -> None:
    assert statement.summary.rfc == "CEL810729LY8"


def test_cuenta_extraida(statement: Statement) -> None:
    assert "177-99743" in statement.summary.cuenta


def test_periodo(statement: Statement) -> None:
    s = statement.summary
    assert s.periodo_inicio.year == 2026
    assert s.periodo_inicio.month == 1
    assert s.periodo_fin.month == 1


def test_saldo_final(statement: Statement) -> None:
    from decimal import Decimal

    assert statement.summary.saldo_final == Decimal("21503.21")


def test_totales_pdf(statement: Statement) -> None:
    from decimal import Decimal

    assert statement.summary.total_abonos == Decimal("5014140.30")
    assert statement.summary.total_cargos == Decimal("5070744.79")


def test_movimientos_no_vacios(statement: Statement) -> None:
    assert len(statement.movements) > 100


def test_cuadre_warnings_conocidos(statement: Statement) -> None:
    """Banregio produce exactamente 2 warnings conocidos por los 440.80 de comisiones."""
    warnings = validar_cuadre(statement)
    assert len(warnings) == 2
    assert _EXPECTED_CARGO_DIFF in warnings[0]


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
