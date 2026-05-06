"""Modelo de estado de la aplicación — sin dependencias de tkinter.

Separar la lógica del estado de los widgets permite:
* Testear el comportamiento de la app sin display.
* Mantener la GUI como una vista "tonta" que sólo refleja este estado.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from bank_parser.core.schema import Statement


class FileStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


_STATUS_ICONS: dict[FileStatus, str] = {
    FileStatus.PENDING: "○",
    FileStatus.PROCESSING: "⟳",
    FileStatus.OK: "✓",
    FileStatus.WARNING: "⚠",
    FileStatus.ERROR: "✗",
}


@dataclass
class FileEntry:
    """Un archivo (PDF/ZIP) cargado en la app con su estado de procesamiento."""

    path: Path
    status: FileStatus = FileStatus.PENDING
    statements: list[Statement] = field(default_factory=list)
    error: str | None = None

    @property
    def status_icon(self) -> str:
        return _STATUS_ICONS[self.status]

    @property
    def rfc_display(self) -> str:
        rfcs = sorted({s.summary.rfc for s in self.statements if s.summary.rfc})
        return ", ".join(rfcs) if rfcs else "(sin RFC)"

    @property
    def bank_display(self) -> str:
        banks = sorted({s.summary.banco.display_name for s in self.statements})
        return ", ".join(banks) if banks else "—"

    @property
    def movement_count(self) -> int:
        return sum(len(s.movements) for s in self.statements)

    @property
    def has_warnings(self) -> bool:
        return any(s.warnings for s in self.statements)


@dataclass
class AppState:
    """Estado global de la aplicación."""

    entries: list[FileEntry] = field(default_factory=list)
    output_dir: Path = field(default_factory=lambda: Path.home() / "Desktop")

    # ------------------------------------------------------------------
    # mutación
    # ------------------------------------------------------------------

    def add_file(self, path: Path) -> FileEntry | None:
        """Agrega un archivo a la lista. Retorna None si ya existía."""
        if any(e.path == path for e in self.entries):
            return None
        entry = FileEntry(path=path)
        self.entries.append(entry)
        return entry

    def remove_file(self, path: Path) -> None:
        self.entries = [e for e in self.entries if e.path != path]

    def clear(self) -> None:
        self.entries.clear()

    # ------------------------------------------------------------------
    # propiedades derivadas
    # ------------------------------------------------------------------

    @property
    def has_files(self) -> bool:
        return bool(self.entries)

    @property
    def is_processing(self) -> bool:
        return any(e.status == FileStatus.PROCESSING for e in self.entries)

    @property
    def processable_entries(self) -> list[FileEntry]:
        return [e for e in self.entries if e.status == FileStatus.PENDING]

    @property
    def can_export(self) -> bool:
        return any(e.status in (FileStatus.OK, FileStatus.WARNING) for e in self.entries)

    @property
    def all_statements(self) -> list[Statement]:
        return [s for e in self.entries for s in e.statements]

    def statements_by_rfc(self) -> dict[str, list[Statement]]:
        """Agrupa todos los statements procesados por RFC."""
        groups: dict[str, list[Statement]] = defaultdict(list)
        for stmt in self.all_statements:
            key = stmt.summary.rfc or "(sin RFC)"
            groups[key].append(stmt)
        return dict(groups)
