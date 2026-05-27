"""Detect the most-frequent RFCs across a list of parsed CFDI rows."""

from __future__ import annotations

from collections import defaultdict

from bank_parser.cfdi_converter.schema import CfdiRow, NominaRow, PagoDocRow

AnyRow = CfdiRow | NominaRow | PagoDocRow

# Generic/placeholder RFCs that should never be suggested as the target company
_GENERIC_RFCS = {"XAXX010101000", "XEXX010101000", ""}


def detect_rfcs(rows: list[AnyRow], top_n: int = 5) -> list[tuple[str, str, int]]:
    """Return (rfc, nombre, count) sorted by total appearance count, highest first.

    Excludes generic SAT placeholder RFCs. The nombre is taken from the first
    occurrence as emisor (more complete) falling back to receptor.
    """
    counts: dict[str, int] = defaultdict(int)
    nombres: dict[str, str] = {}  # rfc → best display name seen so far

    def _record(rfc: str, nombre: str, as_emisor: bool) -> None:
        if rfc in _GENERIC_RFCS:
            return
        counts[rfc] += 1
        if rfc not in nombres or (as_emisor and nombres[rfc] == ""):
            if nombre:
                nombres[rfc] = nombre

    for row in rows:
        if isinstance(row, CfdiRow):
            _record(row.rfc_emisor, row.nombre_emisor, as_emisor=True)
            _record(row.rfc_receptor, row.nombre_receptor, as_emisor=False)
        elif isinstance(row, NominaRow):
            _record(row.rfc_emisor, row.nombre_emisor, as_emisor=True)
            _record(row.rfc_empleado, row.nombre_empleado, as_emisor=False)
        elif isinstance(row, PagoDocRow):
            _record(row.rfc_emisor, row.nombre_emisor, as_emisor=True)
            _record(row.rfc_receptor, row.nombre_receptor, as_emisor=False)

    ranked = sorted(counts.items(), key=lambda x: -x[1])
    return [(rfc, nombres.get(rfc, ""), cnt) for rfc, cnt in ranked[:top_n]]
