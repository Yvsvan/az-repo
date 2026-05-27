"""CFDI XML parser — supports v3.3 and v4.0, nóminas, and complemento pago."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from lxml import etree

from bank_parser.cfdi_converter.schema import CfdiRow, NominaRow, PagoDocRow

_log = logging.getLogger(__name__)

# SAT XML namespaces
_CFDI4 = "http://www.sat.gob.mx/cfd/4"
_CFDI3 = "http://www.sat.gob.mx/cfd/3"
_TFD = "http://www.sat.gob.mx/TimbreFiscalDigital"
_NOM12 = "http://www.sat.gob.mx/nomina12"
_PAGOS20 = "http://www.sat.gob.mx/Pagos20"
_PAGOS10 = "http://www.sat.gob.mx/Pagos"

_TIPO_MAP: dict[str, str] = {
    "I": "Ingreso",
    "E": "Egreso",
    "T": "Traslado",
    "N": "Nómina",
    "P": "Pago",
}

_TIPO_NOMINA_MAP: dict[str, str] = {
    "O": "Ordinaria",
    "E": "Extraordinaria",
}

_FORMA_PAGO: dict[str, str] = {
    "01": "01-Efectivo",
    "02": "02-Cheque nominativo",
    "03": "03-Transferencia electrónica",
    "04": "04-Tarjeta de crédito",
    "05": "05-Monedero electrónico",
    "06": "06-Dinero electrónico",
    "08": "08-Vales de despensa",
    "12": "12-Dación en pago",
    "13": "13-Pago por subrogación",
    "14": "14-Pago por consignación",
    "15": "15-Condonación",
    "17": "17-Compensación",
    "23": "23-Novación",
    "24": "24-Confusión",
    "25": "25-Remisión de deuda",
    "26": "26-Prescripción o caducidad",
    "27": "27-A satisfacción del acreedor",
    "28": "28-Tarjeta de débito",
    "29": "29-Tarjeta de servicio",
    "30": "30-Aplicación de anticipos",
    "31": "31-Intermediario pagos",
    "99": "99-Por definir",
}

CfdiResult = CfdiRow | NominaRow | list[PagoDocRow] | None


def parse_xml(xml_bytes: bytes, filename: str) -> CfdiResult:
    """Parse a single CFDI XML. Returns the appropriate row type, or None on error."""
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        _log.warning("XML malformado %s: %s", filename, exc)
        return None

    ns = _CFDI4 if root.tag.startswith(f"{{{_CFDI4}}}") else _CFDI3
    tipo_code = root.get("TipoDeComprobante", "")

    if tipo_code == "N":
        return _parse_nomina(root, ns, filename)
    if tipo_code == "P":
        return _parse_pagos(root, ns, filename)
    return _parse_factura(root, ns, filename)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _d(val: str | None, default: Decimal = Decimal("0")) -> Decimal:
    if not val:
        return default
    try:
        return Decimal(val)
    except InvalidOperation:
        return default


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val[:19]).date()
    except ValueError:
        return None


def _parse_datetime(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val[:19])
    except ValueError:
        return None


def _get_uuid(root, ns: str) -> str:
    comp = root.find(f"{{{ns}}}Complemento")
    if comp is None:
        return ""
    tfd = comp.find(f"{{{_TFD}}}TimbreFiscalDigital")
    return tfd.get("UUID", "") if tfd is not None else ""


def _get_fecha_timbrado(root, ns: str) -> datetime | None:
    comp = root.find(f"{{{ns}}}Complemento")
    if comp is None:
        return None
    tfd = comp.find(f"{{{_TFD}}}TimbreFiscalDigital")
    return _parse_datetime(tfd.get("FechaTimbrado")) if tfd is not None else None


def _sum_tax(root, ns: str, subtag: str, impuesto_code: str) -> Decimal:
    """Sum Importe of all Traslado/Retencion elements for a given impuesto code."""
    impuestos = root.find(f"{{{ns}}}Impuestos")
    if impuestos is None:
        return Decimal("0")
    total = Decimal("0")
    for item in impuestos.findall(f".//{{{ns}}}{subtag}"):
        if item.get("Impuesto") == impuesto_code:
            total += _d(item.get("Importe"))
    return total


def _parse_factura(root, ns: str, filename: str) -> CfdiRow:
    tipo_code = root.get("TipoDeComprobante", "")
    emisor = root.find(f"{{{ns}}}Emisor")
    receptor = root.find(f"{{{ns}}}Receptor")

    moneda = root.get("Moneda", "MXN")
    tipo_cambio = _d(root.get("TipoCambio", "1")) if moneda != "MXN" else Decimal("1")
    total = _d(root.get("Total"))

    forma_raw = root.get("FormaPago", "")
    forma_pago = _FORMA_PAGO.get(forma_raw, forma_raw)

    conceptos_el = root.find(f"{{{ns}}}Conceptos")
    desc_parts: list[str] = []
    if conceptos_el is not None:
        for c in conceptos_el.findall(f"{{{ns}}}Concepto"):
            d = c.get("Descripcion", "").strip()
            if d and d not in desc_parts:
                desc_parts.append(d)
    descripcion = "; ".join(desc_parts)

    def _rfc_attr(el, attr: str) -> str:
        return el.get(attr, "") if el is not None else ""

    return CfdiRow(
        uuid=_get_uuid(root, ns),
        fecha=_parse_date(root.get("Fecha")),
        fecha_timbrado=_get_fecha_timbrado(root, ns),
        tipo=_TIPO_MAP.get(tipo_code, tipo_code),
        tipo_code=tipo_code,
        serie=root.get("Serie", ""),
        folio=root.get("Folio", ""),
        rfc_emisor=_rfc_attr(emisor, "Rfc"),
        nombre_emisor=_rfc_attr(emisor, "Nombre"),
        regimen_fiscal_emisor=_rfc_attr(emisor, "RegimenFiscal"),
        rfc_receptor=_rfc_attr(receptor, "Rfc"),
        nombre_receptor=_rfc_attr(receptor, "Nombre"),
        uso_cfdi=_rfc_attr(receptor, "UsoCFDI"),
        subtotal=_d(root.get("SubTotal")),
        descuento=_d(root.get("Descuento")),
        iva_trasladado=_sum_tax(root, ns, "Traslado", "002"),
        iva_retenido=_sum_tax(root, ns, "Retencion", "002"),
        isr_retenido=_sum_tax(root, ns, "Retencion", "001"),
        ieps=_sum_tax(root, ns, "Traslado", "003"),
        total=total,
        moneda=moneda,
        tipo_cambio=tipo_cambio,
        total_mxn=total * tipo_cambio,
        forma_pago=forma_pago,
        metodo_pago=root.get("MetodoPago", ""),
        descripcion=descripcion,
        lugar_expedicion=root.get("LugarExpedicion", ""),
        archivo_xml=filename,
    )


def _parse_nomina(root, ns: str, filename: str) -> NominaRow:
    emisor = root.find(f"{{{ns}}}Emisor")
    receptor = root.find(f"{{{ns}}}Receptor")

    comp = root.find(f"{{{ns}}}Complemento")
    nom = comp.find(f"{{{_NOM12}}}Nomina") if comp is not None else None

    tipo_nomina_raw = nom.get("TipoNomina", "") if nom is not None else ""
    fecha_pago_s = nom.get("FechaPago", "") if nom is not None else ""
    fecha_ini = nom.get("FechaInicialPago", "") if nom is not None else ""
    fecha_fin = nom.get("FechaFinalPago", "") if nom is not None else ""
    num_dias = nom.get("NumDiasPagados", "") if nom is not None else ""
    total_perc = nom.get("TotalPercepciones", "") if nom is not None else ""
    total_ded = nom.get("TotalDeducciones", "") if nom is not None else ""
    total_otros = nom.get("TotalOtrosPagos", "") if nom is not None else ""

    curp = num_empleado = departamento = puesto = riesgo_lab = tipo_contrato = ""
    if nom is not None:
        rec_nom = nom.find(f"{{{_NOM12}}}Receptor")
        if rec_nom is not None:
            curp = rec_nom.get("Curp", "")
            num_empleado = rec_nom.get("NumEmpleado", "")
            departamento = rec_nom.get("Departamento", "")
            puesto = rec_nom.get("Puesto", "")
            riesgo_lab = rec_nom.get("RiesgoLab", "")
            tipo_contrato = rec_nom.get("TipoContrato", "")

    def _a(el, attr: str) -> str:
        return el.get(attr, "") if el is not None else ""

    return NominaRow(
        uuid=_get_uuid(root, ns),
        fecha=_parse_date(root.get("Fecha")),
        fecha_timbrado=_get_fecha_timbrado(root, ns),
        rfc_emisor=_a(emisor, "Rfc"),
        nombre_emisor=_a(emisor, "Nombre"),
        rfc_empleado=_a(receptor, "Rfc"),
        nombre_empleado=_a(receptor, "Nombre"),
        curp=curp,
        num_empleado=num_empleado,
        total=_d(root.get("Total")),
        tipo_nomina=_TIPO_NOMINA_MAP.get(tipo_nomina_raw, tipo_nomina_raw),
        fecha_pago=_parse_date(fecha_pago_s),
        fecha_ini_pago=_parse_date(fecha_ini),
        fecha_fin_pago=_parse_date(fecha_fin),
        num_dias_pagados=_d(num_dias),
        total_percepciones=_d(total_perc),
        total_deducciones=_d(total_ded),
        total_otros_pagos=_d(total_otros),
        departamento=departamento,
        puesto=puesto,
        riesgo_lab=riesgo_lab,
        tipo_contrato=tipo_contrato,
        archivo_xml=filename,
    )


def _parse_pagos(root, ns: str, filename: str) -> list[PagoDocRow]:
    emisor = root.find(f"{{{ns}}}Emisor")
    receptor = root.find(f"{{{ns}}}Receptor")
    uuid_pago = _get_uuid(root, ns)
    fecha_base = _parse_date(root.get("Fecha"))

    rfc_emisor = emisor.get("Rfc", "") if emisor is not None else ""
    nombre_emisor = emisor.get("Nombre", "") if emisor is not None else ""
    rfc_receptor = receptor.get("Rfc", "") if receptor is not None else ""
    nombre_receptor = receptor.get("Nombre", "") if receptor is not None else ""

    comp = root.find(f"{{{ns}}}Complemento")
    if comp is None:
        return []

    # Try Pagos 2.0 first, then 1.0
    pagos_ns = _PAGOS20
    pagos_root = comp.find(f"{{{_PAGOS20}}}Pagos")
    if pagos_root is None:
        pagos_ns = _PAGOS10
        pagos_root = comp.find(f"{{{_PAGOS10}}}Pagos")
    if pagos_root is None:
        return []

    rows: list[PagoDocRow] = []

    for pago in pagos_root.findall(f"{{{pagos_ns}}}Pago"):
        fecha_p = _parse_date(pago.get("FechaPago")) or fecha_base
        forma_raw = pago.get("FormaDePagoP", "")
        forma_pago = _FORMA_PAGO.get(forma_raw, forma_raw)
        moneda_p = pago.get("MonedaP", "MXN")
        tipo_cambio_p = _d(pago.get("TipoCambioP", "1")) if moneda_p != "MXN" else Decimal("1")

        docs = pago.findall(f"{{{pagos_ns}}}DoctoRelacionado")
        if docs:
            for doc in docs:
                rows.append(
                    PagoDocRow(
                        uuid_pago=uuid_pago,
                        fecha_pago=fecha_p,
                        rfc_emisor=rfc_emisor,
                        nombre_emisor=nombre_emisor,
                        rfc_receptor=rfc_receptor,
                        nombre_receptor=nombre_receptor,
                        forma_pago=forma_pago,
                        moneda_pago=moneda_p,
                        tipo_cambio_pago=tipo_cambio_p,
                        uuid_relacionado=doc.get("IdDocumento", ""),
                        serie_doc=doc.get("Serie", ""),
                        folio_doc=doc.get("Folio", ""),
                        metodo_pago_doc=doc.get("MetodoDePagoDR", ""),
                        num_parcialidad=doc.get("NumParcialidad", ""),
                        imp_saldo_ant=_d(doc.get("ImpSaldoAnt")),
                        imp_pagado=_d(doc.get("ImpPagado")),
                        imp_saldo_insoluto=_d(doc.get("ImpSaldoInsoluto")),
                        archivo_xml=filename,
                    )
                )
        else:
            # Pago without related documents — keep monto as imp_pagado
            rows.append(
                PagoDocRow(
                    uuid_pago=uuid_pago,
                    fecha_pago=fecha_p,
                    rfc_emisor=rfc_emisor,
                    nombre_emisor=nombre_emisor,
                    rfc_receptor=rfc_receptor,
                    nombre_receptor=nombre_receptor,
                    forma_pago=forma_pago,
                    moneda_pago=moneda_p,
                    tipo_cambio_pago=tipo_cambio_p,
                    uuid_relacionado="",
                    serie_doc="",
                    folio_doc="",
                    metodo_pago_doc="",
                    num_parcialidad="",
                    imp_saldo_ant=Decimal("0"),
                    imp_pagado=_d(pago.get("Monto")),
                    imp_saldo_insoluto=Decimal("0"),
                    archivo_xml=filename,
                )
            )

    return rows
