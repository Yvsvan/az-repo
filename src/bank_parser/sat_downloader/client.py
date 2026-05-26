"""Cliente HTTP para el servicio SOAP SAT Descarga Masiva v1.5."""

from __future__ import annotations

import base64
import logging

import lxml.etree as ET  # noqa: N812
import requests

from bank_parser.sat_downloader._xml_signing import (
    BASE_URL_DESCARGA,
    BASE_URL_SOLICITUD,
    NS_AUTH,
    NS_SAT,
    PATH_AUTH,
    PATH_DESC,
    PATH_SOL,
    PATH_VER,
    SOAP_ACTION_AUTH,
    SOAP_ACTION_DESC,
    SOAP_ACTION_SOL_EMITIDOS,
    SOAP_ACTION_SOL_RECIBIDOS,
    SOAP_ACTION_VER,
    build_auth_envelope,
    build_descarga_envelope,
    build_solicitud_emitidos_envelope,
    build_solicitud_recibidos_envelope,
    build_verifica_envelope,
)
from bank_parser.sat_downloader.schema import EstadoSolicitud, SatCredential, VerificaResponse

log = logging.getLogger(__name__)

_TIMEOUT = 60


class SatApiError(Exception):
    pass


class SatApiClient:
    """Envuelve los 4 endpoints del servicio SAT Descarga Masiva v1.5.

    El servicio v1.5 usa dos hosts distintos:
      - cfdidescargamasivasolicitud.clouda.sat.gob.mx → auth / solicitar / verificar
      - cfdidescargamasiva.clouda.sat.gob.mx           → descargar
    """

    def __init__(
        self,
        base_url: str = BASE_URL_SOLICITUD,
        descarga_url: str = BASE_URL_DESCARGA,
        timeout: int = _TIMEOUT,
    ) -> None:
        self._sol_url = base_url.rstrip("/")
        self._desc_url = descarga_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "text/xml;charset=UTF-8"})
        self._timeout = timeout

    @staticmethod
    def test_connectivity(base_url: str, timeout: int = 10) -> tuple[bool, str]:
        """Verifica que el host SAT sea alcanzable. Retorna (ok, mensaje)."""
        import socket
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            socket.setdefaulttimeout(timeout)
            socket.getaddrinfo(host, port)
            return True, f"Host resuelto: {host}"
        except socket.gaierror as exc:
            return False, f"No se pudo resolver '{host}': {exc}"
        except Exception as exc:
            return False, f"Error de red: {exc}"

    # ------------------------------------------------------------------
    # Operaciones públicas
    # ------------------------------------------------------------------

    def autenticar(self, cred: SatCredential) -> str:
        """Autentica con e.firma y retorna el token de sesión."""
        body = build_auth_envelope(cred.cert_der, cred.private_key)
        root = self._post(self._sol_url + PATH_AUTH, SOAP_ACTION_AUTH, body)
        # v1.5: el elemento de respuesta es AutenticaResult en NS_AUTH
        return self._text(root, f".//{{{NS_AUTH}}}AutenticaResult")

    def solicitar(
        self,
        cred: SatCredential,
        token: str,
        fecha_ini: str,
        fecha_fin: str,
        tipo: str,
    ) -> list[str]:
        """Solicita paquetes de descarga.

        Returns:
            Lista de id_solicitud.  Tiene 1 elemento para E o R, 2 para T.
        """
        ids: list[str] = []
        kw = dict(
            rfc=cred.rfc,
            fecha_ini=fecha_ini,
            fecha_fin=fecha_fin,
            token=token,
            cert_der=cred.cert_der,
            private_key=cred.private_key,
        )

        if tipo in ("E", "T"):
            body = build_solicitud_emitidos_envelope(**kw)
            root = self._post(self._sol_url + PATH_SOL, SOAP_ACTION_SOL_EMITIDOS, body, token)
            ids.append(self._parse_solicitar_result(root, "Emitidos"))

        if tipo in ("R", "T"):
            body = build_solicitud_recibidos_envelope(**kw)
            root = self._post(self._sol_url + PATH_SOL, SOAP_ACTION_SOL_RECIBIDOS, body, token)
            ids.append(self._parse_solicitar_result(root, "Recibidos"))

        if not ids:
            raise SatApiError(f"Tipo de descarga no reconocido: {tipo!r}")
        return ids

    def _parse_solicitar_result(self, root: ET.Element, variant: str) -> str:
        """Extrae IdSolicitud del resultado de SolicitaDescarga{Emitidos|Recibidos}."""
        result = root.find(f".//{{{NS_SAT}}}SolicitaDescarga{variant}Result")
        if result is None:
            # Fallback: buscar cualquier elemento con atributo IdSolicitud
            for el in root.iter():
                if el.get("IdSolicitud"):
                    result = el
                    break
        if result is None:
            raise SatApiError(
                f"Respuesta inesperada de solicitar {variant} — elemento Result no encontrado"
            )
        cod = result.get("CodEstatus", "")
        if cod != "5000":
            msg = result.get("Mensaje", "")
            if cod == "5002":
                msg += (
                    " — Hay solicitudes idénticas pendientes de procesar. "
                    "Espera a que el SAT las complete o usa un rango de fechas diferente."
                )
            elif cod == "5005":
                msg += " — Ya existe una solicitud activa con esos criterios."
            raise SatApiError(f"Solicitud {variant} rechazada ({cod}): {msg}")
        id_sol = result.get("IdSolicitud", "")
        if not id_sol:
            raise SatApiError(f"Solicitud {variant} no retornó IdSolicitud")
        return id_sol

    def verificar(self, cred: SatCredential, token: str, id_solicitud: str) -> VerificaResponse:
        """Consulta el estado de una solicitud."""
        body = build_verifica_envelope(
            id_solicitud, cred.rfc, token, cred.cert_der, cred.private_key
        )
        root = self._post(self._sol_url + PATH_VER, SOAP_ACTION_VER, body, token)
        result = root.find(f".//{{{NS_SAT}}}VerificaSolicitudDescargaResult")
        if result is None:
            raise SatApiError("Respuesta inesperada de /verifica")

        # v1.5: IdsPaquetes como elementos repetidos (string unbounded)
        paquetes = [el.text for el in result.findall(f"{{{NS_SAT}}}IdsPaquetes") if el.text]
        if not paquetes:
            # Compatibilidad: formato antiguo ArrayOfString con hijos <string>
            paquetes = [
                el.text for el in result.findall(f".//{{{NS_SAT}}}IdsPaquetes/string") if el.text
            ]
        if not paquetes:
            # Último intento: <string> en namespace de arrays de Microsoft
            _ns_arrays = "http://schemas.microsoft.com/2003/10/Serialization/Arrays"
            paquetes = [el.text for el in result.iter(f"{{{_ns_arrays}}}string") if el.text]

        return VerificaResponse(
            estado=_parse_estado(result.get("EstadoSolicitud", "4")),
            cod_estatus=result.get("CodEstatus", ""),
            num_cfdis=int(result.get("NumeroCFDIs", "0") or "0"),
            paquetes=paquetes,
            mensaje=result.get("Mensaje", ""),
        )

    def descargar(self, cred: SatCredential, token: str, id_paquete: str) -> bytes:
        """Descarga un paquete y retorna el ZIP en bytes."""
        body = build_descarga_envelope(id_paquete, cred.rfc, token, cred.cert_der, cred.private_key)
        root = self._post(self._desc_url + PATH_DESC, SOAP_ACTION_DESC, body, token)
        paquete_el = root.find(f".//{{{NS_SAT}}}Paquete")
        if paquete_el is None or not paquete_el.text:
            raise SatApiError(f"Paquete vacío para {id_paquete}")
        return base64.b64decode(paquete_el.text.strip())

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _post(self, url: str, action: str, body: bytes, token: str | None = None) -> ET.Element:
        log.debug("SAT REQUEST → %s\n%s", url, body.decode("utf-8", errors="replace"))
        headers = {"SOAPAction": f'"{action}"'}
        if token:
            headers["Authorization"] = f'WRAP access_token="{token}"'
        try:
            resp = self._session.post(url, data=body, headers=headers, timeout=self._timeout)
        except requests.RequestException as exc:
            raise SatApiError(f"Error de red en {url}: {exc}") from exc

        # Intentar extraer detalles del error antes de raise_for_status
        if not resp.ok:
            detail = _extract_fault(resp.content)
            raise SatApiError(
                f"HTTP {resp.status_code} en {url.split('/')[-1]}: {detail or resp.reason}"
            )

        log.debug("SAT RESPONSE ← %s HTTP %s\n%s", url, resp.status_code, resp.text[:2000])
        try:
            root = ET.fromstring(resp.content)
        except ET.XMLSyntaxError as exc:
            raise SatApiError(f"XML inválido en respuesta de {url}: {exc}") from exc

        fault = root.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Fault")
        if fault is not None:
            faultstring = fault.findtext("faultstring") or "desconocido"
            detail_el = fault.find("detail")
            detail_txt = ET.tostring(detail_el, encoding="unicode") if detail_el is not None else ""
            raise SatApiError(
                f"SOAP Fault en {url.split('/')[-1]}: {faultstring} {detail_txt}"[:400]
            )

        return root

    @staticmethod
    def _text(root: ET.Element, xpath: str) -> str:
        el = root.find(xpath)
        if el is None or not el.text:
            raise SatApiError(f"Elemento no encontrado en respuesta: {xpath}")
        return el.text.strip()


def _extract_fault(content: bytes) -> str:
    """Intenta extraer el faultstring de una respuesta SOAP de error."""
    try:
        root = ET.fromstring(content)
        fault = root.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Fault")
        if fault is not None:
            fs = fault.findtext("faultstring") or ""
            detail_el = fault.find("detail")
            detail = ET.tostring(detail_el, encoding="unicode") if detail_el is not None else ""
            return (fs + " " + detail).strip()[:400]
    except Exception:
        pass
    return content.decode("utf-8", errors="replace")[:300]


def _parse_estado(raw: str) -> EstadoSolicitud:
    """Convierte el valor numérico de EstadoSolicitud con manejo de nuevos estados v1.5."""
    try:
        return EstadoSolicitud(int(raw))
    except (ValueError, KeyError):
        return EstadoSolicitud.ERROR
