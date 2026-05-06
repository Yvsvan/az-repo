"""Tests para la lógica pura de AppState (sin GUI ni tkinter).

app_state.py es el único módulo de gui/ con lógica verificable sin display.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from bank_parser.core.schema import BankId, Movement, Statement, StatementSummary
from bank_parser.gui.app_state import AppState, FileEntry, FileStatus

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _make_statement(rfc: str = "RFC123", banco: BankId = BankId.BANAMEX) -> Statement:
    mov = Movement(
        fecha=date(2026, 1, 5),
        descripcion="TEST",
        abono=Decimal("100"),
        cargo=Decimal("0"),
        saldo=Decimal("100"),
        banco=banco,
        cuenta="111",
        archivo_origen="test.pdf",
    )
    summ = StatementSummary(
        banco=banco,
        titular="Empresa SA",
        rfc=rfc,
        cuenta="111",
        periodo_inicio=date(2026, 1, 1),
        periodo_fin=date(2026, 1, 31),
        saldo_inicial=Decimal("0"),
        saldo_final=Decimal("100"),
        total_abonos=Decimal("100"),
        total_cargos=Decimal("0"),
        archivo_origen="test.pdf",
    )
    return Statement(summary=summ, movements=[mov])


# ---------------------------------------------------------------------------
# FileEntry
# ---------------------------------------------------------------------------


class TestFileEntry:
    def test_default_status_is_pending(self, tmp_path: Path) -> None:
        e = FileEntry(path=tmp_path / "a.pdf")
        assert e.status == FileStatus.PENDING

    def test_rfc_display_no_statements(self, tmp_path: Path) -> None:
        e = FileEntry(path=tmp_path / "a.pdf")
        assert "(sin RFC)" in e.rfc_display

    def test_rfc_display_with_statement(self, tmp_path: Path) -> None:
        e = FileEntry(path=tmp_path / "a.pdf", statements=[_make_statement("RFC_ABC")])
        assert "RFC_ABC" in e.rfc_display

    def test_rfc_display_multiple_rfcs(self, tmp_path: Path) -> None:
        e = FileEntry(
            path=tmp_path / "a.pdf",
            statements=[
                _make_statement("RFC_A"),
                _make_statement("RFC_B"),
            ],
        )
        assert "RFC_A" in e.rfc_display
        assert "RFC_B" in e.rfc_display

    def test_rfc_display_none_rfc(self, tmp_path: Path) -> None:
        stmt = _make_statement(rfc="RFC_X")
        # Forzar rfc=None usando model_copy
        stmt_no_rfc = stmt.model_copy(
            update={"summary": stmt.summary.model_copy(update={"rfc": None})}
        )
        e = FileEntry(path=tmp_path / "a.pdf", statements=[stmt_no_rfc])
        assert "(sin RFC)" in e.rfc_display

    def test_bank_display_no_statements(self, tmp_path: Path) -> None:
        e = FileEntry(path=tmp_path / "a.pdf")
        assert e.bank_display == "—"

    def test_bank_display_with_statement(self, tmp_path: Path) -> None:
        e = FileEntry(path=tmp_path / "a.pdf", statements=[_make_statement(banco=BankId.BBVA)])
        assert "BBVA" in e.bank_display

    def test_movement_count(self, tmp_path: Path) -> None:
        stmt = _make_statement()
        e = FileEntry(path=tmp_path / "a.pdf", statements=[stmt, stmt])
        assert e.movement_count == 2  # 1 mov por statement

    def test_has_warnings_false(self, tmp_path: Path) -> None:
        e = FileEntry(path=tmp_path / "a.pdf", statements=[_make_statement()])
        assert not e.has_warnings

    def test_has_warnings_true(self, tmp_path: Path) -> None:
        stmt = _make_statement()
        stmt_warn = stmt.model_copy(update={"warnings": ["cuadre incorrecto"]})
        e = FileEntry(path=tmp_path / "a.pdf", statements=[stmt_warn])
        assert e.has_warnings

    def test_status_icon_pending(self, tmp_path: Path) -> None:
        e = FileEntry(path=tmp_path / "a.pdf")
        icon = e.status_icon
        assert isinstance(icon, str)
        assert len(icon) > 0

    def test_status_icons_differ_across_statuses(self, tmp_path: Path) -> None:
        icons = set()
        for status in FileStatus:
            e = FileEntry(path=tmp_path / "a.pdf", status=status)
            icons.add(e.status_icon)
        # Al menos 3 iconos distintos para los 5 estados
        assert len(icons) >= 3


# ---------------------------------------------------------------------------
# AppState.add_file
# ---------------------------------------------------------------------------


class TestAppStateAddFile:
    def test_add_file_returns_entry(self, tmp_path: Path) -> None:
        state = AppState()
        p = tmp_path / "a.pdf"
        entry = state.add_file(p)
        assert entry is not None
        assert entry.path == p

    def test_add_file_appends_to_entries(self, tmp_path: Path) -> None:
        state = AppState()
        state.add_file(tmp_path / "a.pdf")
        state.add_file(tmp_path / "b.pdf")
        assert len(state.entries) == 2

    def test_add_duplicate_returns_none(self, tmp_path: Path) -> None:
        state = AppState()
        p = tmp_path / "a.pdf"
        state.add_file(p)
        result = state.add_file(p)
        assert result is None
        assert len(state.entries) == 1

    def test_add_different_paths_both_added(self, tmp_path: Path) -> None:
        state = AppState()
        state.add_file(tmp_path / "a.pdf")
        state.add_file(tmp_path / "b.pdf")
        assert len(state.entries) == 2


# ---------------------------------------------------------------------------
# AppState.remove_file / clear
# ---------------------------------------------------------------------------


class TestAppStateRemove:
    def test_remove_existing(self, tmp_path: Path) -> None:
        state = AppState()
        p = tmp_path / "a.pdf"
        state.add_file(p)
        state.remove_file(p)
        assert len(state.entries) == 0

    def test_remove_nonexistent_noop(self, tmp_path: Path) -> None:
        state = AppState()
        state.add_file(tmp_path / "a.pdf")
        state.remove_file(tmp_path / "z.pdf")  # no existe
        assert len(state.entries) == 1

    def test_clear_empties_entries(self, tmp_path: Path) -> None:
        state = AppState()
        state.add_file(tmp_path / "a.pdf")
        state.add_file(tmp_path / "b.pdf")
        state.clear()
        assert len(state.entries) == 0


# ---------------------------------------------------------------------------
# AppState computed properties
# ---------------------------------------------------------------------------


class TestAppStateProperties:
    def test_has_files_false_initially(self) -> None:
        assert not AppState().has_files

    def test_has_files_true_after_add(self, tmp_path: Path) -> None:
        state = AppState()
        state.add_file(tmp_path / "a.pdf")
        assert state.has_files

    def test_can_export_false_when_all_pending(self, tmp_path: Path) -> None:
        state = AppState()
        state.add_file(tmp_path / "a.pdf")
        assert not state.can_export

    def test_can_export_true_when_ok(self, tmp_path: Path) -> None:
        state = AppState()
        entry = state.add_file(tmp_path / "a.pdf")
        entry.status = FileStatus.OK
        entry.statements = [_make_statement()]
        assert state.can_export

    def test_can_export_true_when_warning(self, tmp_path: Path) -> None:
        state = AppState()
        entry = state.add_file(tmp_path / "a.pdf")
        entry.status = FileStatus.WARNING
        entry.statements = [_make_statement()]
        assert state.can_export

    def test_can_export_false_when_only_error(self, tmp_path: Path) -> None:
        state = AppState()
        entry = state.add_file(tmp_path / "a.pdf")
        entry.status = FileStatus.ERROR
        assert not state.can_export

    def test_processable_entries_returns_pending(self, tmp_path: Path) -> None:
        state = AppState()
        e1 = state.add_file(tmp_path / "a.pdf")
        e2 = state.add_file(tmp_path / "b.pdf")
        e2.status = FileStatus.OK
        pending = state.processable_entries
        assert e1 in pending
        assert e2 not in pending

    def test_all_statements_aggregates(self, tmp_path: Path) -> None:
        state = AppState()
        stmt = _make_statement()
        e = state.add_file(tmp_path / "a.pdf")
        e.statements = [stmt, stmt]
        assert len(state.all_statements) == 2

    def test_all_statements_empty_when_no_entries(self) -> None:
        state = AppState()
        assert state.all_statements == []

    def test_statements_by_rfc_groups_correctly(self, tmp_path: Path) -> None:
        state = AppState()
        stmt_a = _make_statement("RFC_A")
        stmt_b = _make_statement("RFC_B")
        e1 = state.add_file(tmp_path / "a.pdf")
        e1.statements = [stmt_a]
        e2 = state.add_file(tmp_path / "b.pdf")
        e2.statements = [stmt_b, stmt_a]  # RFC_B + RFC_A en el mismo archivo
        grouped = state.statements_by_rfc()
        assert "RFC_A" in grouped
        assert "RFC_B" in grouped
        assert len(grouped["RFC_A"]) == 2
        assert len(grouped["RFC_B"]) == 1

    def test_is_processing_false_initially(self) -> None:
        assert not AppState().is_processing

    def test_is_processing_true_when_entry_processing(self, tmp_path: Path) -> None:
        state = AppState()
        entry = state.add_file(tmp_path / "a.pdf")
        entry.status = FileStatus.PROCESSING
        assert state.is_processing


# ---------------------------------------------------------------------------
# AppState.output_dir
# ---------------------------------------------------------------------------


class TestAppStateOutputDir:
    def test_default_output_dir_is_path(self) -> None:
        state = AppState()
        assert isinstance(state.output_dir, Path)

    def test_set_output_dir(self, tmp_path: Path) -> None:
        state = AppState()
        state.output_dir = tmp_path
        assert state.output_dir == tmp_path
