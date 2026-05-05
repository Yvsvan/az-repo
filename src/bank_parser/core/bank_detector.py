"""Deteccion automatica del banco emisor a partir del texto del PDF.

Estrategia: cada banco declara una lista de fingerprints (substrings
case-insensitive). Se cuenta cuantos coinciden por banco y se devuelve
el banco con el match mas alto, siempre que sea inequivoco.

Ventaja sobre matching por la primera coincidencia: si dos bancos
comparten una palabra (p. ej. "BAJIO" puede aparecer como referencia
en un estado de cuenta de BBVA), el banco con mas matches gana.
"""

from __future__ import annotations

from dataclasses import dataclass

from bank_parser.core.exceptions import BankDetectionError
from bank_parser.core.schema import BankId


@dataclass(frozen=True)
class BankFingerprint:
    """Marcadores que identifican univocamente a un banco."""

    bank: BankId
    must_have: tuple[str, ...]
    boosts: tuple[str, ...] = ()


FINGERPRINTS: tuple[BankFingerprint, ...] = (
    BankFingerprint(
        bank=BankId.BANAMEX,
        must_have=("MiCuenta", "banamex.com"),
        boosts=("Centro de Atencion Telefonica",),
    ),
    BankFingerprint(
        bank=BankId.BBVA,
        must_have=("BBVA MEXICO", "GRUPO FINANCIERO BBVA"),
        boosts=("Cash Management", "Paseo de la Reforma 510"),
    ),
    BankFingerprint(
        bank=BankId.BANBAJIO,
        must_have=("BANCO DEL BAJIO", "CUENTA CONECTA BANBAJIO"),
        boosts=("BB.COM.MX",),
    ),
    BankFingerprint(
        bank=BankId.BANREGIO,
        must_have=("Banco Regional", "Banregio Grupo Financiero"),
        boosts=("Detalle de movimientos",),
    ),
    BankFingerprint(
        bank=BankId.BANORTE,
        must_have=("ENLACE NEGOCIOS",),
        boosts=("BANORTE",),
    ),
)


def detect_bank(text: str) -> BankId:
    """Devuelve el BankId del banco emisor del PDF.

    Lanza BankDetectionError si:
    * Ningun fingerprint coincide.
    * Mas de un banco tiene must_have completo y el mismo score (ambiguo).
    """
    candidates: list[tuple[BankId, int]] = []
    text_lower = text.lower()

    for fp in FINGERPRINTS:
        if not all(m.lower() in text_lower for m in fp.must_have):
            continue
        score = len(fp.must_have)
        score += sum(1 for b in fp.boosts if b.lower() in text_lower)
        candidates.append((fp.bank, score))

    if not candidates:
        raise BankDetectionError(
            "No se identifico al banco emisor. Es un estado de cuenta soportado?",
            candidates=[],
        )

    candidates.sort(key=lambda x: x[1], reverse=True)
    top_bank, top_score = candidates[0]

    tied = [c for c in candidates if c[1] == top_score]
    if len(tied) > 1:
        raise BankDetectionError(
            "Multiples bancos coinciden con el PDF; el formato es ambiguo.",
            candidates=[b.display_name for b, _ in tied],
        )

    return top_bank
