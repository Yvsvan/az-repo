"""CLI mínima — útil para iterar parsers sin la GUI.

Imprime un resumen del Statement a stdout.
Con -o acepta .json y .xlsx como salida.
"""

from __future__ import annotations

import sys
from pathlib import Path

from bank_parser.core.exceptions import BankParserError
from bank_parser.core.pipeline import process_file


def run_cli(pdf: Path | None, output: Path | None) -> int:
    """Modo CLI. Devuelve exit code (0 OK, no-cero error)."""
    if pdf is None:
        print("Modo CLI requiere un PDF como argumento.", file=sys.stderr)
        return 2

    try:
        statements = process_file(pdf)
    except BankParserError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for st in statements:
        s = st.summary
        print(f"\n=== {s.banco.display_name} | {s.archivo_origen} ===")
        print(f"Titular:       {s.titular}")
        print(f"RFC:           {s.rfc or '(no detectado)'}")
        print(f"Cuenta:        {s.cuenta}")
        print(f"Periodo:       {s.periodo_inicio} a {s.periodo_fin}")
        print(f"Saldo inicial: {s.saldo_inicial}")
        print(f"Saldo final:   {s.saldo_final}")
        print(f"Total abonos:  {s.total_abonos}")
        print(f"Total cargos:  {s.total_cargos}")
        print(f"# movimientos: {len(st.movements)}")
        if st.warnings:
            print("Warnings:")
            for w in st.warnings:
                print(f"  - {w}")
        if st.movements:
            print("Primeros 3 movimientos:")
            for m in st.movements[:3]:
                tipo = "abono" if m.es_abono else "cargo"
                monto = m.abono if m.es_abono else m.cargo
                desc = m.descripcion[:60]
                print(f"  {m.fecha} | {tipo:5} | {monto:>12} | saldo {m.saldo:>12} | {desc}")

    if output:
        suffix = output.suffix.lower()
        if suffix == ".json":
            from bank_parser.exporters.json_exporter import export_to_json

            export_to_json(statements, output)
            print(f"\n-> JSON exportado a {output}")
        elif suffix == ".xlsx":
            from bank_parser.exporters.excel import export_to_xlsx

            export_to_xlsx(statements, output)
            print(f"\n-> Excel exportado a {output}")
        else:
            print(
                f"Formato '{suffix}' no soportado. Usa .json o .xlsx.",
                file=sys.stderr,
            )
            return 2

    return 0
