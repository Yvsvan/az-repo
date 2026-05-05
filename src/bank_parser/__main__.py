"""Entrypoint del paquete: ``python -m bank_parser``.

Lanza la GUI por defecto. Si se pasa un argumento posicional (un PDF) o
``--cli``, corre en modo línea de comandos.

La GUI se importa lazy para que el modo CLI no requiera ``customtkinter``
en entornos sin display (CI, scripts).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bank-parser",
        description="Parser de estados de cuenta bancarios mexicanos en PDF.",
    )
    p.add_argument(
        "pdf",
        nargs="?",
        type=Path,
        help="Ruta a un PDF o ZIP. Si se omite, se abre la GUI.",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Ruta del archivo de salida (.xlsx o .json). Default: stdout JSON.",
    )
    p.add_argument(
        "--cli",
        action="store_true",
        help="Forzar modo CLI incluso si no se pasa archivo.",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__import__('bank_parser').__version__}",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada del paquete. Retorna el exit code (0 OK)."""
    args = _build_arg_parser().parse_args(argv)

    if args.pdf or args.cli:
        # Importación lazy: el CLI no necesita la GUI.
        from bank_parser.cli import run_cli

        return run_cli(pdf=args.pdf, output=args.output)

    # Sin argumentos → GUI.
    from bank_parser.gui.app import launch_gui

    return launch_gui()


if __name__ == "__main__":
    sys.exit(main())
