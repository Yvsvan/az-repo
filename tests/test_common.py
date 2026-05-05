"""Tests para los helpers compartidos entre parsers."""

from __future__ import annotations

from decimal import Decimal

import pytest

from bank_parser.core.exceptions import ParseError
from bank_parser.parsers._common import extract_rfc, limpiar_numero


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1,234.56", Decimal("1234.56")),
        ("$1,234.56", Decimal("1234.56")),
        ("0.00", Decimal("0.00")),
        ("1234567.89", Decimal("1234567.89")),
        ("  $ 12,345.67 ", Decimal("12345.67")),
    ],
)
def test_limpiar_numero_ok(raw: str, expected: Decimal) -> None:
    assert limpiar_numero(raw) == expected


@pytest.mark.parametrize("bad", ["", "abc", "$", ","])
def test_limpiar_numero_invalido(bad: str) -> None:
    with pytest.raises(ParseError):
        limpiar_numero(bad)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("RFC AUAI000504PN6", "AUAI000504PN6"),  # física, 13 chars
        ("R.F.C. CEL810729LY8", "CEL810729LY8"),  # moral, 12 chars
        ("RFC: GABA880703B17", "GABA880703B17"),
    ],
)
def test_extract_rfc(text: str, expected: str) -> None:
    assert extract_rfc(text) == expected


def test_extract_rfc_no_encontrado() -> None:
    assert extract_rfc("texto sin rfc") is None
