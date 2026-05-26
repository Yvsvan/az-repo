"""Modelos de datos para el módulo SAT Descarga Masiva."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class TipoDescarga(str, Enum):
    EMITIDOS = "E"
    RECIBIDOS = "R"
    TODOS = "T"

    @property
    def display(self) -> str:
        return {"E": "Emitidos", "R": "Recibidos", "T": "Todos"}[self.value]


class EstadoSolicitud(int, Enum):
    ACEPTADA = 1
    EN_PROCESO = 2
    TERMINADA = 3
    ERROR = 4
    RECHAZADA = 5  # v1.5
    VENCIDA = 6  # v1.5


@dataclass
class SatCredential:
    """e.firma cargada y lista para firmar solicitudes."""

    rfc: str
    alias: str
    cer_path: Path
    key_path: Path
    private_key: object = field(default=None, repr=False, compare=False)
    cert_der: bytes = field(default=b"", repr=False, compare=False)

    @property
    def display_name(self) -> str:
        return f"{self.rfc} - {self.alias}" if self.alias and self.alias != self.rfc else self.rfc

    @property
    def is_loaded(self) -> bool:
        return self.private_key is not None


@dataclass
class VerificaResponse:
    estado: EstadoSolicitud
    cod_estatus: str
    num_cfdis: int
    paquetes: list[str]
    mensaje: str = ""


@dataclass
class DownloadResult:
    rfc: str
    total_downloaded: int = 0
    total_skipped_dup: int = 0
    total_errors: int = 0
    packages_ok: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
