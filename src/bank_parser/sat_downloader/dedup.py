"""Detección de duplicados por UUID para CFDIs descargados."""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

_TFD_NS = "http://www.sat.gob.mx/TimbreFiscalDigital"


def scan_existing_uuids(folder: Path) -> set[str]:
    """Lee todos los XMLs en la carpeta y retorna el conjunto de UUIDs ya descargados."""
    uuids: set[str] = set()
    if not folder.exists():
        return uuids
    for xml_path in folder.rglob("*.xml"):
        uid = _uuid_from_file(xml_path)
        if uid:
            uuids.add(uid.upper())
    return uuids


def save_new_xmls(
    zip_bytes: bytes,
    output_folder: Path,
    known_uuids: set[str],
) -> tuple[int, int]:
    """Extrae un ZIP de paquete SAT, guarda XMLs nuevos y omite duplicados.

    Retorna (guardados, omitidos_por_duplicado).
    """
    output_folder.mkdir(parents=True, exist_ok=True)
    saved = skipped = 0

    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if not name.lower().endswith(".xml"):
                    continue
                xml_bytes = zf.read(name)
                uid = _uuid_from_bytes(xml_bytes)
                if uid and uid.upper() in known_uuids:
                    skipped += 1
                    continue
                dest = output_folder / Path(name).name
                # Evitar colisiones de nombre sin UUID
                if dest.exists() and not uid:
                    base = dest.stem
                    ext = dest.suffix
                    counter = 1
                    while dest.exists():
                        dest = output_folder / f"{base}_{counter}{ext}"
                        counter += 1
                dest.write_bytes(xml_bytes)
                if uid:
                    known_uuids.add(uid.upper())
                saved += 1
    except zipfile.BadZipFile:
        pass

    return saved, skipped


def _uuid_from_file(path: Path) -> str | None:
    try:
        return _uuid_from_bytes(path.read_bytes())
    except Exception:
        return None


def _uuid_from_bytes(xml_bytes: bytes) -> str | None:
    try:
        root = ET.fromstring(xml_bytes)
        tfd = root.find(f".//{{{_TFD_NS}}}TimbreFiscalDigital")
        if tfd is not None:
            return tfd.get("UUID")
    except Exception:
        pass
    return None
