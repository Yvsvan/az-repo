"""Configuración persistente de la aplicación (JSON en ~/.az-repo/settings.json)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

_SETTINGS_PATH = Path.home() / ".az-repo" / "settings.json"


@dataclass
class CredentialRef:
    """Referencia a una e.firma guardada (rutas + alias, sin contraseña)."""

    rfc: str
    alias: str
    cer_path: str
    key_path: str


@dataclass
class BankParserSettings:
    output_dir: str = field(default_factory=lambda: str(Path.home() / "Desktop"))
    export_format: Literal["xlsx", "json"] = "xlsx"
    auto_update: bool = True


# URLs del servicio SAT Descarga Masiva v1.5 (activos desde Mayo 2025)
_SAT_API_DEFAULT = "https://cfdidescargamasivasolicitud.clouda.sat.gob.mx"
_SAT_DESCARGA_DEFAULT = "https://cfdidescargamasiva.clouda.sat.gob.mx"


@dataclass
class SatSettings:
    output_dir: str = field(default_factory=lambda: str(Path.home() / "Desktop" / "CFDI"))
    tipo: str = "T"
    poll_interval: int = 20
    sat_api_url: str = _SAT_API_DEFAULT
    sat_descarga_url: str = _SAT_DESCARGA_DEFAULT
    credentials: list[CredentialRef] = field(default_factory=list)


@dataclass
class AppSettings:
    bank: BankParserSettings = field(default_factory=BankParserSettings)
    sat: SatSettings = field(default_factory=SatSettings)
    theme: Literal["dark", "light"] = "dark"

    @classmethod
    def load(cls) -> AppSettings:
        try:
            raw = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
            bank = BankParserSettings(
                **{
                    k: v
                    for k, v in raw.get("bank", {}).items()
                    if k in BankParserSettings.__dataclass_fields__
                }
            )
            sat_raw = raw.get("sat", {})
            creds = [CredentialRef(**c) for c in sat_raw.pop("credentials", [])]
            # Migrar URL obsoleta a la nueva (v1.5 — Mayo 2025)
            _old_url = "https://cfdidescarga.sat.gob.mx/api/offline"
            if sat_raw.get("sat_api_url") == _old_url:
                sat_raw["sat_api_url"] = _SAT_API_DEFAULT
            sat = SatSettings(
                **{k: v for k, v in sat_raw.items() if k in SatSettings.__dataclass_fields__},
                credentials=creds,
            )
            return cls(bank=bank, sat=sat, theme=raw.get("theme", "dark"))
        except Exception:
            return cls()

    def save(self) -> None:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        sat_dict = asdict(self.sat)
        data = {
            "bank": asdict(self.bank),
            "sat": sat_dict,
            "theme": self.theme,
        }
        _SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
