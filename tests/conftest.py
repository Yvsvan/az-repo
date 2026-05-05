"""Fixtures comunes para los tests.

Convenciones:

* ``samples_dir``  → carpeta con PDFs reales por banco.
* ``golden_dir``   → JSON con el ``Statement`` esperado por sample.
* ``regen_golden`` → flag CLI ``--regen-golden`` para regenerar (Fase 1+).
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    return PROJECT_ROOT / "samples"


@pytest.fixture(scope="session")
def golden_dir() -> Path:
    return PROJECT_ROOT / "samples" / "golden"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--regen-golden",
        action="store_true",
        default=False,
        help="Regenerar golden files (úsalo solo cuando un cambio en parser sea legítimo).",
    )


@pytest.fixture(scope="session")
def regen_golden(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--regen-golden"))
