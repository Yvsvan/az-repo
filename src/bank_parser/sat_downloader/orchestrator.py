"""Ciclo completo de descarga: autenticar → solicitar → verificar → descargar."""

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
    paquetes: list[str] = field(default_factory=list)
    result: DownloadResult = field(default_factory=lambda: DownloadResult(rfc=""))


def run_download_session(
    credentials: list[SatCredential],
    fecha_ini: date,
    fecha_fin: date,
    tipo: TipoDescarga,
    output_folder: Path,
    poll_interval: int,
    progress: ProgressCallback,
    cancel: threading.Event,
) -> list[DownloadResult]:
    """
    Descarga multi-cuenta en tres fases:
      1. Autenticar + solicitar para todas las cuentas (rápido, secuencial).
      2. Verificar todas hasta que terminen (polling paralelo).
      3. Descargar paquetes cuenta por cuenta.
    """
    client = SatApiClient()
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

            progress("info", f"[{cred.rfc}] Enviando solicitud de descarga…")
            id_sol = client.solicitar(cred, token, ini_str, fin_str, tipo_str)
            progress("ok", f"[{cred.rfc}] Solicitud aceptada → {id_sol}")

            pending.append(
                _PendingRequest(cred=cred, token=token, id_solicitud=id_sol, result=result)
            )
        except SatApiError as exc:
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
                _log_estado(progress, req.cred.rfc, verif.estado, verif.num_cfdis, verif.mensaje)

                if verif.estado == EstadoSolicitud.TERMINADA:
                    req.paquetes = verif.paquetes
                    done.append(req)
                elif verif.estado == EstadoSolicitud.ERROR:
                    msg = f"Error SAT {verif.cod_estatus}: {verif.mensaje}"
                    req.result.errors.append(msg)
                    progress("error", f"[{req.cred.rfc}] {msg}")
                else:
                    still_pending.append(req)
            except SatApiError as exc:
                progress("warn", f"[{req.cred.rfc}] Error verificando (se reintentará): {exc}")
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
        progress("info", f"[{req.cred.rfc}] Descargando {n} paquete(s)…")
        for i, pkg_id in enumerate(req.paquetes, 1):
            if cancel.is_set():
                break
            progress("info", f"[{req.cred.rfc}] Paquete {i}/{n}: {pkg_id[:16]}…")
            try:
                zip_bytes = client.descargar(req.cred, req.token, pkg_id)
                saved, skipped = save_new_xmls(zip_bytes, output_folder, known_uuids)
                req.result.total_downloaded += saved
                req.result.total_skipped_dup += skipped
                req.result.packages_ok.append(pkg_id)
                progress("ok", f"[{req.cred.rfc}] ✓ {saved} nuevo(s), {skipped} duplicado(s)")
            except SatApiError as exc:
                progress("error", f"[{req.cred.rfc}] Error en paquete {pkg_id[:16]}…: {exc}")
                req.result.total_errors += 1
                req.result.errors.append(str(exc))

    return all_results


def _log_estado(
    progress: ProgressCallback, rfc: str, estado: EstadoSolicitud, n: int, msg: str
) -> None:
    if estado == EstadoSolicitud.ACEPTADA:
        progress("info", f"[{rfc}] Solicitud aceptada, iniciando procesamiento…")
    elif estado == EstadoSolicitud.EN_PROCESO:
        progress("info", f"[{rfc}] Procesando… ({n} CFDI(s) encontrados hasta ahora)")
    elif estado == EstadoSolicitud.TERMINADA:
        progress("ok", f"[{rfc}] Lista: {n} CFDI(s)")


def _interruptible_sleep(seconds: int, cancel: threading.Event) -> None:
    for _ in range(seconds):
        if cancel.is_set():
            return
        time.sleep(1)
