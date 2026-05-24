"""WS-Security XML signing para solicitudes SOAP del SAT Descarga Masiva.

Implementa Exclusive C14N + RSA-SHA256 según el protocolo SAT 2023.
Los endpoints y namespaces son constantes públicas para facilitar ajustes.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import lxml.etree as ET  # noqa: N812
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding

# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------
NS_S = "http://schemas.xmlsoap.org/soap/envelope/"
NS_U = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
NS_O = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"
NS_SAT = "http://DescargaMasivaTerceros.sat.gob.mx"

_BIN_TYPE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3"
_BIN_ENC = (
    "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary"
)
_C14N_EXC = "http://www.w3.org/2001/10/xml-exc-c14n#"
_RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
_SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"

# SAT endpoints (verificar contra la documentación oficial si cambian)
BASE_URL = "https://cfdidescarga.sat.gob.mx/api/offline"
SOAP_ACTION_AUTH = "http://DescargaMasivaTerceros.gob.mx/IDescargaMasivaTercerosAuth/Autenticar"
SOAP_ACTION_SOL = (
    "http://DescargaMasivaTerceros.gob.mx/IDescargaMasivaTercerosSolicitud/SolicitaDescarga"
)
SOAP_ACTION_VER = "http://DescargaMasivaTerceros.gob.mx/IDescargaMasivaTercerosSolicitud/VerificaSolicitudDescarga"
SOAP_ACTION_DESC = (
    "http://DescargaMasivaTerceros.gob.mx/IDescargaMasivaTercerosSolicitud/DescargarPaquete"
)


# ---------------------------------------------------------------------------
# Primitivos de firma
# ---------------------------------------------------------------------------


def _c14n(element: ET.Element) -> bytes:
    """Exclusive XML Canonicalization sin comentarios."""
    return ET.tostring(element, method="c14n", exclusive=True)


def _digest(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def _rsa_sign(data: bytes, private_key) -> str:
    sig = private_key.sign(data, asym_padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


def _make_signed_info(reference_id: str, digest_value: str) -> ET.Element:
    si = ET.Element(f"{{{NS_DS}}}SignedInfo")
    ET.SubElement(si, f"{{{NS_DS}}}CanonicalizationMethod", attrib={"Algorithm": _C14N_EXC})
    ET.SubElement(si, f"{{{NS_DS}}}SignatureMethod", attrib={"Algorithm": _RSA_SHA256})
    ref = ET.SubElement(si, f"{{{NS_DS}}}Reference", attrib={"URI": f"#{reference_id}"})
    transforms = ET.SubElement(ref, f"{{{NS_DS}}}Transforms")
    ET.SubElement(transforms, f"{{{NS_DS}}}Transform", attrib={"Algorithm": _C14N_EXC})
    ET.SubElement(ref, f"{{{NS_DS}}}DigestMethod", attrib={"Algorithm": _SHA256})
    ET.SubElement(ref, f"{{{NS_DS}}}DigestValue").text = digest_value
    return si


def _build_signature(signed_info: ET.Element, private_key, token_id: str) -> ET.Element:
    sig_value = _rsa_sign(_c14n(signed_info), private_key)
    sig = ET.Element(f"{{{NS_DS}}}Signature")
    sig.append(signed_info)
    ET.SubElement(sig, f"{{{NS_DS}}}SignatureValue").text = sig_value
    ki = ET.SubElement(sig, f"{{{NS_DS}}}KeyInfo")
    str_ref = ET.SubElement(ki, f"{{{NS_O}}}SecurityTokenReference")
    ET.SubElement(
        str_ref,
        f"{{{NS_O}}}Reference",
        attrib={
            "URI": f"#{token_id}",
            "ValueType": _BIN_TYPE,
        },
    )
    return sig


def _make_security_header(cert_der: bytes, token_id: str) -> ET.Element:
    cert_b64 = base64.b64encode(cert_der).decode()
    security = ET.Element(
        f"{{{NS_O}}}Security",
        attrib={f"{{{NS_S}}}mustUnderstand": "1"},
        nsmap={"o": NS_O, "u": NS_U},
    )
    bst = ET.SubElement(
        security,
        f"{{{NS_O}}}BinarySecurityToken",
        attrib={
            f"{{{NS_U}}}Id": token_id,
            "ValueType": _BIN_TYPE,
            "EncodingType": _BIN_ENC,
        },
    )
    bst.text = cert_b64
    return security


def _wrap_envelope(header_children: list[ET.Element], body_child: ET.Element) -> bytes:
    nsmap = {"s": NS_S, "u": NS_U}
    envelope = ET.Element(f"{{{NS_S}}}Envelope", nsmap=nsmap)
    header = ET.SubElement(envelope, f"{{{NS_S}}}Header")
    for child in header_children:
        header.append(child)
    body = ET.SubElement(envelope, f"{{{NS_S}}}Body")
    body.append(body_child)
    return ET.tostring(envelope, xml_declaration=True, encoding="UTF-8")


# ---------------------------------------------------------------------------
# Constructores de envelopes
# ---------------------------------------------------------------------------


def build_auth_envelope(cert_der: bytes, private_key) -> bytes:
    """Envelope SOAP firmado para /autenticacion."""
    now = datetime.now(timezone.utc)
    ts_id = "_0"
    token_id = f"uuid-{uuid.uuid4()}"

    ts = ET.Element(f"{{{NS_U}}}Timestamp", attrib={f"{{{NS_U}}}Id": ts_id})
    ET.SubElement(ts, f"{{{NS_U}}}Created").text = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    ET.SubElement(ts, f"{{{NS_U}}}Expires").text = (now + timedelta(minutes=5)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )

    si = _make_signed_info(ts_id, _digest(_c14n(ts)))
    sig = _build_signature(si, private_key, token_id)

    security = _make_security_header(cert_der, token_id)
    security.insert(0, ts)
    security.append(sig)

    body_child = ET.Element(f"{{{NS_SAT}}}Autenticar")
    return _wrap_envelope([security], body_child)


def build_solicitud_envelope(
    rfc: str,
    fecha_ini: str,
    fecha_fin: str,
    tipo: str,
    token: str,
    cert_der: bytes,
    private_key,
) -> bytes:
    """Envelope SOAP firmado para /solicita."""
    sol_id = f"_sol{uuid.uuid4().hex[:8]}"
    token_id = f"uuid-{uuid.uuid4()}"

    attribs = {
        "RfcSolicitante": rfc,
        "FechaInicial": fecha_ini,
        "FechaFinal": fecha_fin,
        "TipoSolicitud": "CFDI",
        "Id": sol_id,
    }
    if tipo == "E":
        attribs["RfcEmisor"] = rfc
    elif tipo == "R":
        attribs["RfcReceptores"] = rfc

    solicitud = ET.Element(f"{{{NS_SAT}}}solicitud", attrib=attribs)
    si = _make_signed_info(sol_id, _digest(_c14n(solicitud)))
    sig = _build_signature(si, private_key, token_id)
    solicitud.append(sig)

    security = _make_security_header(cert_der, token_id)
    body_child = ET.Element(f"{{{NS_SAT}}}SolicitaDescarga")
    body_child.append(solicitud)
    return _wrap_envelope([security], body_child)


def build_verifica_envelope(
    id_solicitud: str,
    rfc: str,
    token: str,
    cert_der: bytes,
    private_key,
) -> bytes:
    """Envelope SOAP firmado para /verifica."""
    ver_id = f"_ver{uuid.uuid4().hex[:8]}"
    token_id = f"uuid-{uuid.uuid4()}"

    verifica = ET.Element(
        f"{{{NS_SAT}}}verifica",
        attrib={
            "RfcSolicitante": rfc,
            "IdSolicitud": id_solicitud,
            "Id": ver_id,
        },
    )
    si = _make_signed_info(ver_id, _digest(_c14n(verifica)))
    sig = _build_signature(si, private_key, token_id)
    verifica.append(sig)

    security = _make_security_header(cert_der, token_id)
    body_child = ET.Element(f"{{{NS_SAT}}}VerificaSolicitudDescarga")
    body_child.append(verifica)
    return _wrap_envelope([security], body_child)


def build_descarga_envelope(
    id_paquete: str,
    rfc: str,
    token: str,
    cert_der: bytes,
    private_key,
) -> bytes:
    """Envelope SOAP firmado para /descarga."""
    desc_id = f"_desc{uuid.uuid4().hex[:8]}"
    token_id = f"uuid-{uuid.uuid4()}"

    descarga = ET.Element(
        f"{{{NS_SAT}}}peticionDescarga",
        attrib={
            "RfcSolicitante": rfc,
            "IdPaquete": id_paquete,
            "Id": desc_id,
        },
    )
    si = _make_signed_info(desc_id, _digest(_c14n(descarga)))
    sig = _build_signature(si, private_key, token_id)
    descarga.append(sig)

    security = _make_security_header(cert_der, token_id)
    body_child = ET.Element(f"{{{NS_SAT}}}DescargarPaquete")
    body_child.append(descarga)
    return _wrap_envelope([security], body_child)
