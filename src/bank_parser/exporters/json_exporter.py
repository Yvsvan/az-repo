"""Exportador a JSON.

Usa la serialización nativa de pydantic (``model_dump_json``), que ya
maneja ``Decimal``, ``date`` y los enums correctamente.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from bank_parser.core.schema import Statement


def export_to_json(
    statements: Sequence[Statement],
    output_path: Path | str,
    *,
    indent: int = 2,
) -> Path:
    """Serializa uno o varios :class:`Statement` a un archivo JSON.

    Args:
        statements: Lista de estados de cuenta parseados.
        output_path: Ruta destino. Los directorios intermedios se crean.
        indent: Sangría del JSON (default 2).

    Returns:
        El :class:`Path` del archivo generado.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # pydantic serializa Decimal como string por defecto; usamos mode="json"
    # para obtener tipos nativos JSON y luego volcamos con json.dumps.
    payload = [json.loads(s.model_dump_json()) for s in statements]
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=indent),
        encoding="utf-8",
    )
    return output_path


def export_single_to_json(
    statement: Statement,
    output_path: Path | str,
    *,
    indent: int = 2,
) -> Path:
    """Serializa un único :class:`Statement` (sin envolver en lista)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        statement.model_dump_json(indent=indent),
        encoding="utf-8",
    )
    return output_path
