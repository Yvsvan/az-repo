"""Tests para el exportador JSON."""

from __future__ import annotations

import json
from pathlib import Path

from bank_parser.core.schema import Statement
from bank_parser.exporters.json_exporter import export_single_to_json, export_to_json


def test_returns_path(tmp_path: Path, sample_statement: Statement) -> None:
    result = export_to_json([sample_statement], tmp_path / "out.json")
    assert isinstance(result, Path)
    assert result.exists()


def test_creates_parent_dirs(tmp_path: Path, sample_statement: Statement) -> None:
    dest = tmp_path / "deep" / "nested" / "out.json"
    export_to_json([sample_statement], dest)
    assert dest.exists()


def test_output_is_list(tmp_path: Path, sample_statement: Statement) -> None:
    path = export_to_json([sample_statement], tmp_path / "out.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 1


def test_multiple_statements(tmp_path: Path, two_statements_diff_rfc: list[Statement]) -> None:
    path = export_to_json(two_statements_diff_rfc, tmp_path / "out.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == 2


def test_movements_present(tmp_path: Path, sample_statement: Statement) -> None:
    path = export_to_json([sample_statement], tmp_path / "out.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "movements" in data[0]
    assert len(data[0]["movements"]) == len(sample_statement.movements)


def test_rfc_in_summary(tmp_path: Path, sample_statement: Statement) -> None:
    path = export_to_json([sample_statement], tmp_path / "out.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[0]["summary"]["rfc"] == sample_statement.summary.rfc


def test_single_export_not_wrapped_in_list(tmp_path: Path, sample_statement: Statement) -> None:
    path = export_single_to_json(sample_statement, tmp_path / "single.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "summary" in data
    assert "movements" in data


def test_utf8_encoding(tmp_path: Path, sample_statement: Statement) -> None:
    """El archivo debe ser UTF-8 y contener caracteres no ASCII correctamente."""
    path = export_to_json([sample_statement], tmp_path / "out.json")
    raw = path.read_bytes()
    # Sin BOM, decodificable como UTF-8
    decoded = raw.decode("utf-8")
    assert "Empresa Ejemplo SA de CV" in decoded
