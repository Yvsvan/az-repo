"""Dataclasses for parsed CFDI rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass
class CfdiRow:
    """One row per invoice (Ingreso, Egreso, Traslado)."""

    uuid: str
    fecha: date | None
    fecha_timbrado: datetime | None
    tipo: str  # human-readable: Ingreso, Egreso, Traslado
    tipo_code: str  # raw SAT code: I, E, T
    serie: str
    folio: str
    rfc_emisor: str
    nombre_emisor: str
    regimen_fiscal_emisor: str
    rfc_receptor: str
    nombre_receptor: str
    uso_cfdi: str
    subtotal: Decimal
    descuento: Decimal
    iva_trasladado: Decimal
    iva_retenido: Decimal
    isr_retenido: Decimal
    ieps: Decimal
    total: Decimal
    moneda: str
    tipo_cambio: Decimal
    total_mxn: Decimal
    forma_pago: str
    metodo_pago: str
    descripcion: str
    lugar_expedicion: str
    archivo_xml: str


@dataclass
class NominaRow:
    """One row per nómina CFDI (TipoDeComprobante = N)."""

    uuid: str
    fecha: date | None
    fecha_timbrado: datetime | None
    rfc_emisor: str
    nombre_emisor: str
    rfc_empleado: str
    nombre_empleado: str
    curp: str
    num_empleado: str
    total: Decimal
    tipo_nomina: str  # Ordinaria / Extraordinaria
    fecha_pago: date | None
    fecha_ini_pago: date | None
    fecha_fin_pago: date | None
    num_dias_pagados: Decimal
    total_percepciones: Decimal
    total_deducciones: Decimal
    total_otros_pagos: Decimal
    departamento: str
    puesto: str
    riesgo_lab: str
    tipo_contrato: str
    archivo_xml: str


@dataclass
class PagoDocRow:
    """One row per DoctoRelacionado inside a Complemento Pago CFDI (P)."""

    uuid_pago: str
    fecha_pago: date | None
    rfc_emisor: str
    nombre_emisor: str
    rfc_receptor: str
    nombre_receptor: str
    forma_pago: str
    moneda_pago: str
    tipo_cambio_pago: Decimal
    uuid_relacionado: str
    serie_doc: str
    folio_doc: str
    metodo_pago_doc: str
    num_parcialidad: str
    imp_saldo_ant: Decimal
    imp_pagado: Decimal
    imp_saldo_insoluto: Decimal
    archivo_xml: str
