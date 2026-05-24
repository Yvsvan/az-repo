"""Cliente HTTP para el servicio SOAP SAT Descarga Masiva."""

from __future__ import annotations

import base64

import lxml.etree as ET  # noqa: N812
import requests

from bank_parser.sat_downloader._xml_signing import (
    BASE_URL,
    NS_SAT,
    SOAP_ACTION_AUTH,
    SOAP_ACTION_DESC,
    SOAP_ACTION_SOL,
    SOAP_ACTION_VER,
    build_auth_envelope,
    build_descarga_envelope,
    build_solicitud_envelope,
    build_verifica_envelope,
)
from bank_parser.sat_downloader.schema import EstadoSolicitud, SatCredential, VerificaResponse

_TIMEOUT = 60


class SatApiError(Exception):
    pass


class SatApiClient:
    """Envuelve los 4 endpoints del servicio SAT Descarga Masiva."""

    def __init__(self, timeout: int = _TIMEOUT) -> None:
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "text/xml;charset=UTF-8"})
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Operaciones públicas
    # ------------------------------------------------------------------

    def autenticar(self, cred: SatCredential) -> str:
        """Autentica con e.firma y retorna el token de sesión."""
        body = build_auth_envelope(cred.cert_der, cred.private_key)
        root = self._post("/autenticacion", SOAP_ACTION_AUTH, body)
        return self._text(root, f".//{{{NS_SAT}}}AutenticarResult")

    def solicitar(
        self,
        cred: SatCredential,
        token: str,
        fecha_ini: str,
        fecha_fin: str,
        tipo: str,
    ) -> str:
        """Solicita un paquete de descarga. Retorna id_solicitud."""
        body = build_solicitud_envelope(
            cred.rfc, fecha_ini, fecha_fin, tipo, token, cred.cert_der, cred.private_key
        )
        root = self._post("/solicita", SOAP_ACTION_SOL, body, token)
        result = root.find(f".//{{{NS_SAT}}}SolicitaDescargaResult")
        if result is None:
            raise SatApiError("Respuesta inesperada de /solicita — elemento Result no encontrado")
        cod = result.get("CodEstatus", "")
        if cod != "5000":
            raise SatApiError(f"Solicitud rechazada ({cod}): {result.get('Mensaje', '')}")
        return result.get("IdSolicitud", "")

    def verificar(self, cred: SatCredential, token: str, id_solicitud: str) -> VerificaResponse:
        """Consulta el estado de una solicitud."""
        body = build_verifica_envelope(
            id_solicitud, cred.rfc, token, cred.cert_der, cred.private_key
        )
        root = self._post("/verifica", SOAP_ACTION_VER, body, token)
        result = root.find(f".//{{{NS_SAT}}}VerificaSolicitudDescargaResult")
        if result is None:
            raise SatApiError("Respuesta inesperada de /verifica")
        paquetes = [
            el.text for el in result.findall(f".//{{{NS_SAT}}}IdsPaquetes/string") if el.text
        ]
        return VerificaResponse(
            estado=EstadoSolicitud(int(result.get("EstadoSolicitud", "4"))),
            cod_estatus=result.get("CodEstatus", ""),
            num_cfdis=int(result.get("NumeroCFDIs", "0") or "0"),
            paquetes=paquetes,
            mensaje=result.get("Mensaje", ""),
        )

    def descargar(self, cred: SatCredential, token: str, id_paquete: str) -> bytes:
        """Descarga un paquete y retorna el ZIP en bytes."""
        body = build_descarga_envelope(id_paquete, cred.rfc, token, cred.cert_der, cred.private_key)
        root = self._post("/descarga", SOAP_ACTION_DESC, body, token)
        paquete_el = root.find(f".//{{{NS_SAT}}}Paquete")
        if paquete_el is None or not paquete_el.text:
            raise SatApiError(f"Paquete vacío para {id_paquete}")
        return base64.b64decode(paquete_el.text.strip())

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _post(self, path: str, action: str, body: bytes, token: str | None = None) -> ET.Element:
        headers = {"SOAPAction": f'"{action}"'}
        if token:
            headers["Authorization"] = f'WRAP access_token="{token}"'
        try:
            resp = self._session.post(
                BASE_URL + path, data=body, headers=headers, timeout=self._timeout
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise SatApiError(f"Error de red en {path}: {exc}") from exc

        try:
            root = ET.fromstring(resp.content)
        except ET.XMLSyntaxError as exc:
            raise SatApiError(f"XML inválido en respuesta de {path}: {exc}") from exc

        fault = root.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Fault")
        if fault is not None:
            faultstring = fault.findtext("faultstring") or "desconocido"
            raise SatApiError(f"SOAP Fault en {path}: {faultstring}")

        return root

    @staticmethod
    def _text(root: ET.Element, xpath: str) -> str:
        el = root.find(xpath)
        if el is None or not el.text:
            raise SatApiError(f"Elemento no encontrado en respuesta: {xpath}")
        return el.text.strip()
