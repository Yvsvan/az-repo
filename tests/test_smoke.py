"""Smoke test: el paquete se importa correctamente.

Sirve para que la suite no esté vacía durante la Fase 0 y para detectar
errores triviales (typos en imports, módulos rotos) en CI.
"""

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
