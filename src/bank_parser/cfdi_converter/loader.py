"""Load CFDI XMLs from ZIP files and/or directories."""

from __future__ import annotations

import logging
import zipfile
from collections.abc import Callable
from pathlib import Path

from bank_parser.cfdi_converter.parser import parse_xml
from bank_parser.cfdi_converter.schema import CfdiRow, NominaRow, PagoDocRow

_log = logging.getLogger(__name__)

AnyRow = CfdiRow | NominaRow | PagoDocRow
ProgressCb = Callable[[str, str], None]  # (message, level)


def load_sources(
    paths: list[Path],
    progress_cb: ProgressCb | None = None,
) -> list[AnyRow]:
    """Parse all XMLs from the given ZIPs and/or folders. Deduplicates by UUID."""
    seen: set[str] = set()
    rows: list[AnyRow] = []

    def _cb(msg: str, level: str = "info") -> None:
        if progress_cb:
            progress_cb(msg, level)
        _log.debug(msg)

    for path in paths:
        if not path.exists():
            _cb(f"No encontrado: {path}", "warn")
            continue

        if path.is_dir():
            xml_files = sorted(path.rglob("*.xml"))
            _cb(f"Carpeta {path.name}: {len(xml_files)} XMLs encontrados")
            for xml_path in xml_files:
                try:
                    _process(xml_path.read_bytes(), xml_path.name, seen, rows, _cb)
                except OSError as exc:
                    _cb(f"  Error leyendo {xml_path.name}: {exc}", "warn")

        elif path.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
                    _cb(f"ZIP {path.name}: {len(xml_names)} XMLs")
                    for name in xml_names:
                        _process(zf.read(name), Path(name).name, seen, rows, _cb)
            except zipfile.BadZipFile:
                _cb(f"ZIP inválido: {path.name}", "warn")
            except OSError as exc:
                _cb(f"Error abriendo {path.name}: {exc}", "warn")

        else:
            _cb(f"Formato no soportado (se esperan .zip o carpeta): {path.name}", "warn")

    return rows


def _process(
    data: bytes,
    filename: str,
    seen: set[str],
    rows: list[AnyRow],
    cb: ProgressCb,
) -> None:
    result = parse_xml(data, filename)
    if result is None:
        cb(f"  Error al parsear: {filename}", "warn")
        return

    if isinstance(result, list):
        added = 0
        for row in result:
            key = f"{row.uuid_pago}|{row.uuid_relacionado}|{row.num_parcialidad}"
            if key not in seen:
                seen.add(key)
                rows.append(row)
                added += 1
        if added:
            cb(f"  ✓ {filename} ({added} doc(s) de pago)", "ok")
        else:
            cb(f"  Duplicado: {filename}")
    elif isinstance(result, NominaRow):
        if result.uuid not in seen:
            seen.add(result.uuid)
            rows.append(result)
            cb(f"  ✓ {filename} (Nómina)", "ok")
        else:
            cb(f"  Duplicado: {filename}")
    else:
        if result.uuid not in seen:
            seen.add(result.uuid)
            rows.append(result)
            cb(f"  ✓ {filename} ({result.tipo})", "ok")
        else:
            cb(f"  Duplicado: {filename}")
