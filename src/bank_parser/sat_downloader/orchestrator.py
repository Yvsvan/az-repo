"""Ciclo completo de descarga v1.5: autenticar → solicitar → verificar → descargar."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from bank_parser.sat_downloader.client import SatApiClient, SatApiError
from bank_parser.sat_downloader.dedup import save_new_xmls, scan_existing_uuids
from bank_parser.sat_downloader.schema import (
    DownloadResult,
    EstadoSolicitud,
    SatCredential,
    TipoDescarga,
)

ProgressCallback = Callable[[str, str], None]  # (level, message)


@dataclass
class _PendingRequest:
    cred: SatCredential
    token: str
    id_solicitud: str
    label: str  # "Emitidos" | "Recibidos" | "E/R"
    paquetes: list[str] = field(default_factory=list)
    result: DownloadResult = field(default_factory=lambda: DownloadResult(rfc=""))
    _sat_error_retries: int = field(default=0, repr=False)


def run_download_session(
    credentials: list[SatCredential],
    fecha_ini: date,
    fecha_fin: date,
    tipo: TipoDescarga,
    output_folder: Path,
    poll_interval: int,
    progress: ProgressCallback,
    cancel: threading.Event,
    sat_api_url: str | None = None,
    sat_descarga_url: str | None = None,
) -> list[DownloadResult]:
    """
    Descarga multi-cuenta en tres fases (v1.5):
      1. Autenticar + solicitar para todas las cuentas (rápido, secuencial).
         Para tipo T se crean dos solicitudes por cuenta (Emitidos + Recibidos).
      2. Verificar todas hasta que terminen (polling secuencial con pausa).
      3. Descargar paquetes cuenta por cuenta.
    """
    from bank_parser.sat_downloader._xml_signing import BASE_URL_DESCARGA, BASE_URL_SOLICITUD

    sol_url = sat_api_url or BASE_URL_SOLICITUD
    desc_url = sat_descarga_url or BASE_URL_DESCARGA
    client = SatApiClient(base_url=sol_url, descarga_url=desc_url)

    ini_str = fecha_ini.strftime("%Y-%m-%dT00:00:00")
    fin_str = fecha_fin.strftime("%Y-%m-%dT23:59:59")
    tipo_str = tipo.value if isinstance(tipo, TipoDescarga) else tipo

    # Fase 1: autenticar + solicitar
    pending: list[_PendingRequest] = []
    all_results: list[DownloadResult] = []

    for cred in credentials:
        if cancel.is_set():
            break
        result = DownloadResult(rfc=cred.rfc)
        all_results.append(result)
        try:
            progress("info", f"[{cred.rfc}] Autenticando…")
            token = client.autenticar(cred)
            progress("ok", f"[{cred.rfc}] Token obtenido")
        except SatApiError as exc:
            progress("error", f"[{cred.rfc}] Error de autenticación: {exc}")
            result.errors.append(str(exc))
            continue

        # Para tipo T se hacen dos solicitudes independientes (E y R).
        # Si Recibidos falla (ej. error 301 "cancelados"), se registra como
        # advertencia pero Emitidos continúa.  Para E/R la falla es fatal.
        sub_tipos: list[tuple[str, str]]  # (tipo_llamada, label)
        if tipo_str == "T":
            sub_tipos = [("E", "Emitidos"), ("R", "Recibidos")]
        elif tipo_str == "E":
            sub_tipos = [("E", "Emitidos")]
        else:
            sub_tipos = [("R", "Recibidos")]

        for sub_tipo, label in sub_tipos:
            if cancel.is_set():
                break
            progress("info", f"[{cred.rfc}] Enviando solicitud {label}…")
            try:
                sub_ids = client.solicitar(cred, token, ini_str, fin_str, sub_tipo)
                for id_sol in sub_ids:
                    progress("ok", f"[{cred.rfc}] Solicitud {label} aceptada → {id_sol}")
                    pending.append(
                        _PendingRequest(
                            cred=cred,
                            token=token,
                            id_solicitud=id_sol,
                            label=label,
                            result=result,
                        )
                    )
            except SatApiError as exc:
                if tipo_str == "T":
                    # Para "Todos", Recibidos es opcional: loguear y continuar
                    progress("warn", f"[{cred.rfc}] Solicitud {label} omitida: {exc}")
                    result.errors.append(f"Solicitud {label} omitida: {exc}")
                else:
                    progress("error", f"[{cred.rfc}] {exc}")
                    result.errors.append(str(exc))

    if not pending or cancel.is_set():
        return all_results

    # Fase 2: verificar todas en conjunto
    progress("info", f"Verificando {len(pending)} solicitud(es) cada {poll_interval}s…")
    done: list[_PendingRequest] = []

    while pending and not cancel.is_set():
        still_pending: list[_PendingRequest] = []
        for req in pending:
            if cancel.is_set():
                break
            try:
                verif = client.verificar(req.cred, req.token, req.id_solicitud)
                _log_estado(
                    progress,
                    req.cred.rfc,
                    req.label,
                    verif.estado,
                    verif.num_cfdis,
                    verif.mensaje,
                )

                if verif.estado == EstadoSolicitud.TERMINADA:
                    req.paquetes = verif.paquetes
                    done.append(req)
                elif verif.cod_estatus == "300":
                    # Token expirado — re-autenticar y continuar en el siguiente ciclo
                    progress(
                        "warn", f"[{req.cred.rfc}/{req.label}] Token expirado, re-autenticando…"
                    )
                    try:
                        new_token = client.autenticar(req.cred)
                        # Actualizar token en todas las solicitudes del mismo RFC
                        for r in [*still_pending, req]:
                            if r.cred.rfc == req.cred.rfc:
                                r.token = new_token
                        req.token = new_token
                        still_pending.append(req)
                    except SatApiError as auth_exc:
                        progress(
                            "error",
                            f"[{req.cred.rfc}/{req.label}] Re-autenticación fallida: {auth_exc}",
                        )
                        req.result.errors.append(str(auth_exc))
                elif verif.cod_estatus == "404":
                    # Error interno transitorio del SAT — reintentar hasta 3 veces
                    req._sat_error_retries += 1
                    if req._sat_error_retries <= 3:
                        progress(
                            "warn",
                            f"[{req.cred.rfc}/{req.label}] SAT error transitorio (404), reintento {req._sat_error_retries}/3…",
                        )
                        still_pending.append(req)
                    else:
                        progress(
                            "warn",
                            f"[{req.cred.rfc}/{req.label}] SAT error 404 persistente tras 3 reintentos — omitiendo solicitud",
                        )
                elif verif.estado in (
                    EstadoSolicitud.ERROR,
                    EstadoSolicitud.RECHAZADA,
                    EstadoSolicitud.VENCIDA,
                ):
                    msg = f"Estado {verif.estado.name} ({verif.cod_estatus}): {verif.mensaje}"
                    req.result.errors.append(msg)
                    progress("error", f"[{req.cred.rfc}/{req.label}] {msg}")
                else:
                    still_pending.append(req)
            except SatApiError as exc:
                progress(
                    "warn", f"[{req.cred.rfc}/{req.label}] Error verificando (reintento): {exc}"
                )
                still_pending.append(req)

        pending = still_pending
        if pending:
            _interruptible_sleep(poll_interval, cancel)

    # Fase 3: descargar paquetes
    known_uuids = scan_existing_uuids(output_folder)
    progress("info", f"UUIDs ya en carpeta: {len(known_uuids)} — se omitirán duplicados")

    for req in done:
        if cancel.is_set():
            break
        n = len(req.paquetes)
        progress("info", f"[{req.cred.rfc}/{req.label}] Descargando {n} paquete(s)…")
        for i, pkg_id in enumerate(req.paquetes, 1):
            if cancel.is_set():
                break
            progress("info", f"[{req.cred.rfc}/{req.label}] Paquete {i}/{n}: {pkg_id[:16]}…")
            try:
                zip_bytes = client.descargar(req.cred, req.token, pkg_id)
            except SatApiError as exc:
                if "300" in str(exc) or "Token" in str(exc):
                    try:
                        req.token = client.autenticar(req.cred)
                        zip_bytes = client.descargar(req.cred, req.token, pkg_id)
                    except SatApiError as exc2:
                        progress(
                            "error",
                            f"[{req.cred.rfc}/{req.label}] Error paquete {pkg_id[:16]}…: {exc2}",
                        )
                        req.result.total_errors += 1
                        req.result.errors.append(str(exc2))
                        continue
                else:
                    progress(
                        "error", f"[{req.cred.rfc}/{req.label}] Error paquete {pkg_id[:16]}…: {exc}"
                    )
                    req.result.total_errors += 1
                    req.result.errors.append(str(exc))
                    continue
            saved, skipped = save_new_xmls(zip_bytes, output_folder, known_uuids)
            req.result.total_downloaded += saved
            req.result.total_skipped_dup += skipped
            req.result.packages_ok.append(pkg_id)
            progress("ok", f"[{req.cred.rfc}/{req.label}] ✓ {saved} nuevo(s), {skipped} dup(s)")

    return all_results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _solicitud_labels(tipo: str, count: int) -> list[str]:
    if tipo == "E":
        return ["Emitidos"]
    if tipo == "R":
        return ["Recibidos"]
    if tipo == "T" and count == 2:
        return ["Emitidos", "Recibidos"]
    return [f"Solicitud {i + 1}" for i in range(count)]


def _log_estado(
    progress: ProgressCallback,
    rfc: str,
    label: str,
    estado: EstadoSolicitud,
    n: int,
    msg: str,
) -> None:
    tag = f"[{rfc}/{label}]"
    if estado == EstadoSolicitud.ACEPTADA:
        progress("info", f"{tag} Solicitud aceptada, iniciando procesamiento…")
    elif estado == EstadoSolicitud.EN_PROCESO:
        progress("info", f"{tag} Procesando… ({n} CFDI(s) encontrados hasta ahora)")
    elif estado == EstadoSolicitud.TERMINADA:
        progress("ok", f"{tag} Lista: {n} CFDI(s)")
    elif estado == EstadoSolicitud.RECHAZADA:
        progress("warn", f"{tag} Solicitud rechazada por el SAT: {msg}")
    elif estado == EstadoSolicitud.VENCIDA:
        progress("warn", f"{tag} Solicitud vencida (superó las 72 h): {msg}")


def _interruptible_sleep(seconds: int, cancel: threading.Event) -> None:
    for _ in range(seconds):
        if cancel.is_set():
            return
        time.sleep(1)
