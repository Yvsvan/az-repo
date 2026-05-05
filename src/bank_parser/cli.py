"""CLI minima -- util para iterar parsers sin la GUI.

Imprime un resumen del Statement a stdout. Si se pasa -o con extension
.json exporta JSON; .xlsx se implementa en Fase 3.
"""

from __future__ import annotations

import json
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
        if output.suffix.lower() == ".json":
            output.parent.mkdir(parents=True, exist_ok=True)
            data = [json.loads(st.model_dump_json()) for st in statements]
            output.write_text(
                json.dumps(data, indent=2, ensure_ascii=False, default=str)
            )
            print(f"\n-> JSON exportado a {output}")
        else:
            print(
                f"Formato {output.suffix} aun no soportado por la CLI (Fase 3).",
                file=sys.stderr,
            )
            return 2

    return 0
