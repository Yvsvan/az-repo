"""Fixtures para tests de exporters."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from bank_parser.core.schema import BankId, Movement, Statement, StatementSummary


def _mov(
    fecha: date,
    desc: str,
    abono: str = "0",
    cargo: str = "0",
    saldo: str = "0",
    banco: BankId = BankId.BANAMEX,
    cuenta: str = "1234567890",
    archivo: str = "test.pdf",
) -> Movement:
    return Movement(
        fecha=fecha,
        descripcion=desc,
        abono=Decimal(abono),
        cargo=Decimal(cargo),
        saldo=Decimal(saldo),
        banco=banco,
        cuenta=cuenta,
        archivo_origen=archivo,
    )


def _summary(
    banco: BankId = BankId.BANAMEX,
    rfc: str | None = "RFC123456789",
    cuenta: str = "1234567890",
    saldo_inicial: str = "1000.00",
    saldo_final: str = "1500.00",
    total_abonos: str = "600.00",
    total_cargos: str = "100.00",
    archivo: str = "test.pdf",
) -> StatementSummary:
    return StatementSummary(
        banco=banco,
        titular="Empresa Ejemplo SA de CV",
        rfc=rfc,
        cuenta=cuenta,
        periodo_inicio=date(2026, 1, 1),
        periodo_fin=date(2026, 1, 31),
        saldo_inicial=Decimal(saldo_inicial),
        saldo_final=Decimal(saldo_final),
        total_abonos=Decimal(total_abonos),
        total_cargos=Decimal(total_cargos),
        archivo_origen=archivo,
    )


@pytest.fixture()
def sample_statement() -> Statement:
    """Statement simple de Banamex con RFC conocido."""
    movs = [
        _mov(date(2026, 1, 5), "DEPOSITO CLIENTE", abono="500.00", saldo="1500.00"),
        _mov(date(2026, 1, 10), "PAGO PROVEEDOR", cargo="100.00", saldo="1400.00"),
        _mov(date(2026, 1, 20), "TRANSFERENCIA RECIBIDA", abono="100.00", saldo="1500.00"),
    ]
    return Statement(summary=_summary(), movements=movs)


@pytest.fixture()
def statement_with_warnings() -> Statement:
    """Statement con advertencias (warnings)."""
    movs = [
        _mov(date(2026, 1, 5), "DEPOSITO", abono="200.00", saldo="1200.00"),
    ]
    summ = _summary(saldo_final="1300.00")  # cuadre incorrecto a propósito
    return Statement(
        summary=summ,
        movements=movs,
        warnings=["Cuadre incompleto: diferencia de 100.00", "Formato inusual en página 3"],
    )


@pytest.fixture()
def statement_bbva() -> Statement:
    """Statement de BBVA con RFC distinto."""
    movs = [
        _mov(
            date(2026, 2, 1),
            "SPEI RECIBIDO",
            abono="10000.00",
            saldo="10000.00",
            banco=BankId.BBVA,
            cuenta="0987654321",
            archivo="bbva_feb2026.pdf",
        ),
        _mov(
            date(2026, 2, 15),
            "COMISION MANEJO",
            cargo="300.00",
            saldo="9700.00",
            banco=BankId.BBVA,
            cuenta="0987654321",
            archivo="bbva_feb2026.pdf",
        ),
    ]
    summ = _summary(
        banco=BankId.BBVA,
        rfc="RFC999888777",
        cuenta="0987654321",
        saldo_inicial="0.00",
        saldo_final="9700.00",
        total_abonos="10000.00",
        total_cargos="300.00",
        archivo="bbva_feb2026.pdf",
    )
    return Statement(summary=summ, movements=movs)


@pytest.fixture()
def two_statements_same_rfc(sample_statement: Statement) -> list[Statement]:
    """Dos statements del mismo RFC (Banamex enero + febrero)."""
    movs_feb = [
        _mov(date(2026, 2, 3), "COBRO SERVICIO", abono="800.00", saldo="2300.00"),
        _mov(date(2026, 2, 18), "RETIRO ATM", cargo="500.00", saldo="1800.00"),
    ]
    summ_feb = _summary(
        saldo_inicial="1500.00",
        saldo_final="1800.00",
        total_abonos="800.00",
        total_cargos="500.00",
        archivo="banamex_feb2026.pdf",
    )
    stmt_feb = Statement(summary=summ_feb, movements=movs_feb)
    return [sample_statement, stmt_feb]


@pytest.fixture()
def two_statements_diff_rfc(
    sample_statement: Statement, statement_bbva: Statement
) -> list[Statement]:
    """Dos statements de distinto RFC."""
    return [sample_statement, statement_bbva]


@pytest.fixture()
def statement_no_rfc() -> Statement:
    """Statement sin RFC (rfc=None)."""
    movs = [
        _mov(date(2026, 3, 1), "DEPOSITO SIN RFC", abono="100.00", saldo="100.00"),
    ]
    summ = _summary(rfc=None, archivo="sin_rfc.pdf")
    return Statement(summary=summ, movements=movs)
