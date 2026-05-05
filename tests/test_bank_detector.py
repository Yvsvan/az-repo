"""Tests del detector de bancos."""

from __future__ import annotations

import pytest

from bank_parser.core.bank_detector import detect_bank
from bank_parser.core.exceptions import BankDetectionError
from bank_parser.core.schema import BankId


def test_detecta_banamex() -> None:
    text = "Estado de Cuenta\nMiCuenta\nbanamex.com\nCentro de Atención Telefónica"
    assert detect_bank(text) == BankId.BANAMEX


def test_detecta_bbva() -> None:
    text = (
        "Estado de Cuenta\nBBVA MEXICO, S.A.\nGRUPO FINANCIERO BBVA MEXICO\n"
        "Cash Management ..."
    )
    assert detect_bank(text) == BankId.BBVA


def test_detecta_banbajio() -> None:
    text = "BANCO DEL BAJIO\nCUENTA CONECTA BANBAJIO\nBB.COM.MX"
    assert detect_bank(text) == BankId.BANBAJIO


def test_detecta_banregio() -> None:
    text = "Banco Regional, S.A.\nBanregio Grupo Financiero\nDetalle de movimientos"
    assert detect_bank(text) == BankId.BANREGIO


def test_detecta_banorte() -> None:
    text = "ESTADO DE CUENTA / ENLACE NEGOCIOS BASICA\nBANORTE\nResumen"
    assert detect_bank(text) == BankId.BANORTE


def test_falla_sin_match() -> None:
    with pytest.raises(BankDetectionError) as excinfo:
        detect_bank("Texto cualquiera sin marcadores bancarios")
    assert excinfo.value.candidates == []


def test_marcador_de_bbva_en_referencia_no_confunde_a_banbajio() -> None:
    """Si en un PDF de BBVA aparece la palabra 'BAJIO' como referencia de
    una transferencia, no debe ganar BanBajío."""
    text = (
        "BBVA MEXICO, S.A. GRUPO FINANCIERO BBVA MEXICO\nCash Management M.N.\n"
        "01/FEB 03/FEB BT3 TRANSF SPEI BAJIO 13,850.00\n"
    )
    assert detect_bank(text) == BankId.BBVA


def test_referencia_a_bbva_en_pdf_de_banamex_no_confunde() -> None:
    """En un PDF de Banamex aparece 'PAGO RECIBIDO DE BBVA MEXICO' como
    referencia de transferencia. No debe disparar BBVA."""
    text = (
        "Estado de Cuenta\nMiCuenta\nbanamex.com\n"
        "17 MAR PAGO RECIBIDO DE BBVA MEXICO\nPOR ORDEN DE ANA\n"
    )
    assert detect_bank(text) == BankId.BANAMEX
