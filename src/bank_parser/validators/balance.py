"""Validador de cuadre numérico: ``saldo_inicial + abonos - cargos = saldo_final``.

No lanza excepción por defecto: registra warnings en el ``Statement``
para que la GUI los muestre y el usuario decida exportar igual o no.
La filosofía es **fail soft**: un cuadre incorrecto puede deberse a un
campo opcional faltante en el PDF, no necesariamente a un parser roto.

Si el caller quiere fallar duro, puede inspeccionar ``warnings`` y
abortar.
"""

from __future__ import annotations

from decimal import Decimal

from bank_parser.core.schema import Statement

# Tolerancia: 0.01 cubre redondeos legítimos. Más que eso es sospechoso.
_TOLERANCIA = Decimal("0.01")


def validar_cuadre(statement: Statement) -> list[str]:
    """Calcula warnings de cuadre. Devuelve lista (vacía si todo OK)."""
    warnings: list[str] = []
    s = statement.summary

    # 1) Suma de movimientos vs totales del PDF.
    suma_abonos = sum((m.abono for m in statement.movements), start=Decimal("0"))
    suma_cargos = sum((m.cargo for m in statement.movements), start=Decimal("0"))

    if abs(suma_abonos - s.total_abonos) > _TOLERANCIA:
        warnings.append(
            f"Σ abonos calculada ({suma_abonos}) no coincide con el total reportado "
            f"({s.total_abonos}). Diferencia: {suma_abonos - s.total_abonos}."
        )
    if abs(suma_cargos - s.total_cargos) > _TOLERANCIA:
        warnings.append(
            f"Σ cargos calculada ({suma_cargos}) no coincide con el total reportado "
            f"({s.total_cargos}). Diferencia: {suma_cargos - s.total_cargos}."
        )

    # 2) Identidad del saldo: inicial + abonos - cargos = final.
    saldo_calculado = s.saldo_inicial + suma_abonos - suma_cargos
    if abs(saldo_calculado - s.saldo_final) > _TOLERANCIA:
        warnings.append(
            f"Cuadre del saldo falló: inicial ({s.saldo_inicial}) + abonos "
            f"({suma_abonos}) - cargos ({suma_cargos}) = {saldo_calculado}, "
            f"pero el PDF reporta saldo final {s.saldo_final}. "
            f"Diferencia: {saldo_calculado - s.saldo_final}."
        )

    # 3) Cantidad mínima razonable de movimientos.
    if statement.movements == [] and (s.total_abonos > 0 or s.total_cargos > 0):
        warnings.append(
            "El resumen reporta movimientos pero no se extrajo ninguno. "
            "El parser necesita revisión."
        )

    return warnings
