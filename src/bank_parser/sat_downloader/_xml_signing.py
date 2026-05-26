"""WS-Security XML signing para solicitudes SOAP del SAT Descarga Masiva v1.5.

Implementa Exclusive C14N + RSA-SHA1 según el protocolo SAT v1.5 (2025-05-30).
Los endpoints y namespaces son constantes públicas para facilitar ajustes.

Cambios v1.5 respecto a v1.0:
  - Nuevos hosts: cfdidescargamasivasolicitud.clouda.sat.gob.mx / cfdidescargamasiva.clouda.sat.gob.mx
  - Auth usa namespace http://DescargaMasivaTerceros.gob.mx (diferente a NS_SAT)
  - Solicitar dividido en SolicitaDescargaEmitidos / SolicitaDescargaRecibidos
  - Verificar usa elemento <solicitud> en lugar de <verifica>
  - Descargar usa PeticionDescargaMasivaTercerosEntrada como wrapper
  - Algoritmo de firma: RSA-SHA1 (confirmado por implementaciones de referencia satcfdi/phpcfdi)
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
NS_SAT = "http://DescargaMasivaTerceros.sat.gob.mx"  # solicitar / verificar / descargar
NS_AUTH = "http://DescargaMasivaTerceros.gob.mx"  # autenticación (v1.5)

_BIN_TYPE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3"
_BIN_ENC = (
    "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary"
)
_C14N_EXC = "http://www.w3.org/2001/10/xml-exc-c14n#"
_RSA_SHA1 = "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
_SHA1 = "http://www.w3.org/2000/09/xmldsig#sha1"
_ENV_SIG = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"

# SAT v1.5 endpoints (verificados contra WSDL activo, Mayo 2025)
BASE_URL_SOLICITUD = "https://cfdidescargamasivasolicitud.clouda.sat.gob.mx"
BASE_URL_DESCARGA = "https://cfdidescargamasiva.clouda.sat.gob.mx"
BASE_URL = BASE_URL_SOLICITUD  # alias de compatibilidad para settings

# Paths de cada servicio
PATH_AUTH = "/Autenticacion/Autenticacion.svc"
PATH_SOL = "/SolicitaDescargaService.svc"
PATH_VER = "/VerificaSolicitudDescargaService.svc"
PATH_DESC = "/DescargaMasivaService.svc"

# SOAP Actions v1.5 — confirmadas contra el WSDL activo del SAT
# El servicio tiene DOS operaciones distintas (no una única SolicitaDescarga)
SOAP_ACTION_AUTH = "http://DescargaMasivaTerceros.gob.mx/IAutenticacion/Autentica"
SOAP_ACTION_SOL_EMITIDOS = (
    "http://DescargaMasivaTerceros.sat.gob.mx/ISolicitaDescargaService/SolicitaDescargaEmitidos"
)
SOAP_ACTION_SOL_RECIBIDOS = (
    "http://DescargaMasivaTerceros.sat.gob.mx/ISolicitaDescargaService/SolicitaDescargaRecibidos"
)
SOAP_ACTION_SOL = SOAP_ACTION_SOL_EMITIDOS  # alias de compatibilidad
SOAP_ACTION_VER = (
    "http://DescargaMasivaTerceros.sat.gob.mx"
    "/IVerificaSolicitudDescargaService/VerificaSolicitudDescarga"
)
SOAP_ACTION_DESC = (
    "http://DescargaMasivaTerceros.sat.gob.mx/IDescargaMasivaTercerosService/Descargar"
)


# ---------------------------------------------------------------------------
# Primitivos de firma
# ---------------------------------------------------------------------------


def _c14n(element: ET.Element) -> bytes:
    """Exclusive XML Canonicalization sin comentarios."""
    return ET.tostring(element, method="c14n", exclusive=True)


def _digest(data: bytes) -> str:
    return base64.b64encode(hashlib.sha1(data).digest()).decode()


def _rsa_sign(data: bytes, private_key) -> str:
    sig = private_key.sign(data, asym_padding.PKCS1v15(), hashes.SHA1())
    return base64.b64encode(sig).decode()


def _make_signed_info(
    reference_uri: str, digest_value: str, *, enveloped: bool = False
) -> ET.Element:
    """Construye el elemento SignedInfo.

    Args:
        reference_uri: URI del Reference ("" = documento completo para solicitar;
                       "#id" = elemento específico para verifica/descarga/auth).
        digest_value:  Digest SHA-1 en Base64 del elemento canonicalizado.
        enveloped:     True → agrega transform enveloped-signature ANTES de exc-c14n.
                       Usado por verifica/descarga donde Signature queda dentro
                       del elemento referenciado por "#id".
                       Solicitar usa URI="" sin enveloped (solo exc-c14n).
    """
    si = ET.Element(f"{{{NS_DS}}}SignedInfo")
    ET.SubElement(si, f"{{{NS_DS}}}CanonicalizationMethod", attrib={"Algorithm": _C14N_EXC})
    ET.SubElement(si, f"{{{NS_DS}}}SignatureMethod", attrib={"Algorithm": _RSA_SHA1})
    ref = ET.SubElement(si, f"{{{NS_DS}}}Reference", attrib={"URI": reference_uri})
    transforms = ET.SubElement(ref, f"{{{NS_DS}}}Transforms")
    if enveloped:
        ET.SubElement(transforms, f"{{{NS_DS}}}Transform", attrib={"Algorithm": _ENV_SIG})
    ET.SubElement(transforms, f"{{{NS_DS}}}Transform", attrib={"Algorithm": _C14N_EXC})
    ET.SubElement(ref, f"{{{NS_DS}}}DigestMethod", attrib={"Algorithm": _SHA1})
    ET.SubElement(ref, f"{{{NS_DS}}}DigestValue").text = digest_value
    return si


def _build_signature(
    signed_info: ET.Element,
    private_key,
    *,
    token_id: str | None = None,
    cert_der: bytes | None = None,
) -> ET.Element:
    """Construye el elemento ds:Signature completo.

    Dos modos de KeyInfo:
    - token_id  → o:SecurityTokenReference → #token_id (usado en auth, donde el
                  Security header con WS-Security registra el BST en el contexto).
    - cert_der  → ds:X509Data/X509Certificate con el certificado embebido (usado en
                  solicitar/verificar/descargar, donde el Security header tiene
                  mustUnderstand='0' y el verificador SAT extrae el cert directamente
                  del KeyInfo según el XSD del servicio).
    """
    sig_value = _rsa_sign(_c14n(signed_info), private_key)
    sig = ET.Element(f"{{{NS_DS}}}Signature")
    sig.append(signed_info)
    ET.SubElement(sig, f"{{{NS_DS}}}SignatureValue").text = sig_value
    ki = ET.SubElement(sig, f"{{{NS_DS}}}KeyInfo")
    if cert_der is not None:
        x509 = ET.SubElement(ki, f"{{{NS_DS}}}X509Data")
        ET.SubElement(x509, f"{{{NS_DS}}}X509Certificate").text = base64.b64encode(
            cert_der
        ).decode()
    else:
        str_ref = ET.SubElement(ki, f"{{{NS_O}}}SecurityTokenReference")
        ET.SubElement(
            str_ref,
            f"{{{NS_O}}}Reference",
            attrib={"URI": f"#{token_id}", "ValueType": _BIN_TYPE},
        )
    return sig


def _make_security_header(cert_der: bytes, token_id: str) -> ET.Element:
    cert_b64 = base64.b64encode(cert_der).decode()
    # mustUnderstand="0": los endpoints solicitar/verificar/descargar usan binding
    # personalizado (HTTP Authorization + firma en body); mustUnderstand="1" provoca
    # que WCF lance MustUnderstandException al no tener WS-Security configurado.
    security = ET.Element(
        f"{{{NS_O}}}Security",
        attrib={f"{{{NS_S}}}mustUnderstand": "0"},
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
# Constructores de envelopes (v1.5)
# ---------------------------------------------------------------------------


def build_auth_envelope(cert_der: bytes, private_key) -> bytes:
    """Envelope SOAP firmado para /Autenticacion/Autenticacion.svc (v1.5).

    IMPORTANTE: el digest del Timestamp se calcula DESPUÉS de insertarlo en el elemento
    Security (que declara xmlns:u), de forma que el prefijo canónico coincide con lo que
    el servidor SAT verifica.  Calcular el digest sobre el elemento standalone produce
    xmlns:ns0 en lugar de xmlns:u → digest diferente → SOAP Fault 500.
    """
    now = datetime.now(timezone.utc)
    ts_id = "_0"
    token_id = "BinarySecurityToken"

    # Paso 1: construir Security con Timestamp ya en contexto (xmlns:u declarado aquí)
    security = ET.Element(
        f"{{{NS_O}}}Security",
        attrib={f"{{{NS_S}}}mustUnderstand": "1"},
        nsmap={"o": NS_O, "u": NS_U},
    )
    ts = ET.SubElement(security, f"{{{NS_U}}}Timestamp", attrib={f"{{{NS_U}}}Id": ts_id})
    ET.SubElement(ts, f"{{{NS_U}}}Created").text = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    ET.SubElement(ts, f"{{{NS_U}}}Expires").text = (now + timedelta(minutes=5)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )

    # BinarySecurityToken también en contexto
    cert_b64 = base64.b64encode(cert_der).decode()
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

    # Paso 2: digest del Timestamp IN-CONTEXT (prefijo u:, no ns0:)
    ts_digest = _digest(_c14n(ts))

    # Paso 3: firmar (auth: Signature en Security header, BST en mismo header → token_id)
    si = _make_signed_info(f"#{ts_id}", ts_digest)
    sig = _build_signature(si, private_key, token_id=token_id)
    security.append(sig)

    # v1.5: body element usa NS_AUTH (http://DescargaMasivaTerceros.gob.mx)
    body_child = ET.Element(f"{{{NS_AUTH}}}Autentica")
    return _wrap_envelope([security], body_child)


def build_solicitud_emitidos_envelope(
    rfc: str,
    fecha_ini: str,
    fecha_fin: str,
    token: str,
    cert_der: bytes,
    private_key,
) -> bytes:
    """Envelope SOAP firmado para SolicitaDescargaEmitidos (v1.5).

    Estructura confirmada contra WSDL y phpcfdi:
    - Body wrapper: SolicitaDescargaEmitidos
    - RfcEmisor como atributo en <solicitud>
    - Firma: Reference URI="" + solo exc-c14n transform (sin enveloped-signature)
    - Digest calculado sobre c14n(<solicitud>) ANTES de insertar ds:Signature
    """
    token_id = "BinarySecurityToken"

    solicitud = ET.Element(
        f"{{{NS_SAT}}}solicitud",
        attrib={
            "FechaFinal": fecha_fin,
            "FechaInicial": fecha_ini,
            "RfcEmisor": rfc,
            "RfcSolicitante": rfc,
            "TipoSolicitud": "CFDI",
        },
    )
    si = _make_signed_info("", _digest(_c14n(solicitud)))
    sig = _build_signature(si, private_key, cert_der=cert_der)
    solicitud.append(sig)

    security = _make_security_header(cert_der, token_id)
    body_child = ET.Element(f"{{{NS_SAT}}}SolicitaDescargaEmitidos")
    body_child.append(solicitud)
    return _wrap_envelope([security], body_child)


def build_solicitud_recibidos_envelope(
    rfc: str,
    fecha_ini: str,
    fecha_fin: str,
    token: str,
    cert_der: bytes,
    private_key,
) -> bytes:
    """Envelope SOAP firmado para SolicitaDescargaRecibidos (v1.5).

    Estructura confirmada contra WSDL y phpcfdi:
    - Body wrapper: SolicitaDescargaRecibidos
    - RfcReceptor como ATRIBUTO en <solicitud> (no elemento hijo)
    - EstadoComprobante="Vigente" obligatorio para TipoSolicitud="CFDI"
      (Todos/Cancelado → error 301 en modo CFDI)
    - Firma: Reference URI="" + solo exc-c14n transform (sin enveloped-signature)
    - Digest calculado sobre c14n(<solicitud>) ANTES de insertar ds:Signature
    """
    token_id = "BinarySecurityToken"

    solicitud = ET.Element(
        f"{{{NS_SAT}}}solicitud",
        attrib={
            "EstadoComprobante": "Vigente",
            "FechaFinal": fecha_fin,
            "FechaInicial": fecha_ini,
            "RfcReceptor": rfc,
            "RfcSolicitante": rfc,
            "TipoSolicitud": "CFDI",
        },
    )
    si = _make_signed_info("", _digest(_c14n(solicitud)))
    sig = _build_signature(si, private_key, cert_der=cert_der)
    solicitud.append(sig)

    security = _make_security_header(cert_der, token_id)
    body_child = ET.Element(f"{{{NS_SAT}}}SolicitaDescargaRecibidos")
    body_child.append(solicitud)
    return _wrap_envelope([security], body_child)


# Alias para importaciones que usen el nombre genérico
build_solicitud_envelope = build_solicitud_emitidos_envelope


def build_verifica_envelope(
    id_solicitud: str,
    rfc: str,
    token: str,
    cert_der: bytes,
    private_key,
) -> bytes:
    """Envelope SOAP firmado para VerificaSolicitudDescargaService (v1.5)."""
    ver_id = f"_ver{uuid.uuid4().hex[:8]}"
    token_id = "BinarySecurityToken"

    # v1.5: elemento interno se llama <solicitud> (antes era <verifica>)
    solicitud = ET.Element(
        f"{{{NS_SAT}}}solicitud",
        attrib={
            "IdSolicitud": id_solicitud,
            "RfcSolicitante": rfc,
            "Id": ver_id,
        },
    )
    si = _make_signed_info(f"#{ver_id}", _digest(_c14n(solicitud)), enveloped=True)
    sig = _build_signature(si, private_key, cert_der=cert_der)
    solicitud.append(sig)

    security = _make_security_header(cert_der, token_id)
    body_child = ET.Element(f"{{{NS_SAT}}}VerificaSolicitudDescarga")
    body_child.append(solicitud)
    return _wrap_envelope([security], body_child)


def build_descarga_envelope(
    id_paquete: str,
    rfc: str,
    token: str,
    cert_der: bytes,
    private_key,
) -> bytes:
    """Envelope SOAP firmado para DescargaMasivaService (v1.5)."""
    desc_id = f"_desc{uuid.uuid4().hex[:8]}"
    token_id = "BinarySecurityToken"

    peticion = ET.Element(
        f"{{{NS_SAT}}}peticionDescarga",
        attrib={
            "RfcSolicitante": rfc,
            "IdPaquete": id_paquete,
            "Id": desc_id,
        },
    )
    si = _make_signed_info(f"#{desc_id}", _digest(_c14n(peticion)), enveloped=True)
    sig = _build_signature(si, private_key, cert_der=cert_der)
    peticion.append(sig)

    security = _make_security_header(cert_der, token_id)
    # v1.5: wrapper es PeticionDescargaMasivaTercerosEntrada (antes DescargarPaquete)
    body_child = ET.Element(f"{{{NS_SAT}}}PeticionDescargaMasivaTercerosEntrada")
    body_child.append(peticion)
    return _wrap_envelope([security], body_child)
