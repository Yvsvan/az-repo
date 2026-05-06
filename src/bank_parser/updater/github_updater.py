"""Auto-update vía GitHub Releases.

Flujo:
1. Al arrancar la app, se llama ``check_for_update`` en un hilo de fondo.
2. Si hay versión nueva, devuelve un ``UpdateInfo``; la GUI muestra un banner.
3. Al confirmar, se abre la página del release en el navegador o se descarga
   directamente con ``download_release``.

Nunca lanza excepciones hacia el caller: todos los errores de red, JSON
malformado, etc. se capturan y producen ``None`` / retornos seguros.
"""

from __future__ import annotations

import hashlib
import tempfile
import webbrowser
from dataclasses import dataclass
from pathlib import Path

import requests
from packaging.version import InvalidVersion, Version

# URL de la API de GitHub para el último release publicado.
_API_URL = "https://api.github.com/repos/{repo}/releases/latest"
_GITHUB_HEADERS = {"Accept": "application/vnd.github+json"}
_DEFAULT_TIMEOUT = 5  # segundos


# ---------------------------------------------------------------------------
# Tipos públicos
# ---------------------------------------------------------------------------


@dataclass
class UpdateInfo:
    """Información sobre una actualización disponible."""

    current: str
    latest: str
    download_url: str
    sha256_url: str | None
    release_url: str

    @property
    def is_newer(self) -> bool:
        try:
            return Version(self.latest) > Version(self.current)
        except InvalidVersion:
            return False

    @property
    def display_message(self) -> str:
        return f"Nueva versión disponible: {self.latest}  " f"(tienes la {self.current})"


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def parse_latest_version(tag: str) -> str | None:
    """Limpia el prefijo 'v' y valida semver. Retorna None si es inválido."""
    cleaned = tag.lstrip("v").strip()
    if not cleaned:
        return None
    try:
        Version(cleaned)
        return cleaned
    except InvalidVersion:
        return None


def check_for_update(
    repo: str,
    current_version: str,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
) -> UpdateInfo | None:
    """Consulta GitHub Releases y retorna info si hay versión más nueva.

    Args:
        repo: ``"usuario/repositorio"`` de GitHub.
        current_version: Versión instalada (sin prefijo ``v``).
        timeout: Tiempo máximo de espera para la petición HTTP.

    Returns:
        :class:`UpdateInfo` si hay versión más nueva, ``None`` si está
        actualizado o si ocurrió cualquier error.
    """
    try:
        resp = requests.get(
            _API_URL.format(repo=repo),
            headers=_GITHUB_HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    tag = data.get("tag_name", "")
    latest = parse_latest_version(tag)
    if latest is None:
        return None

    try:
        if Version(latest) <= Version(current_version):
            return None
    except InvalidVersion:
        return None

    release_url: str = data.get("html_url", "")
    assets: list[dict] = data.get("assets", [])

    zip_url: str | None = None
    sha256_url: str | None = None
    for asset in assets:
        name: str = asset.get("name", "")
        url: str = asset.get("browser_download_url", "")
        if name.endswith(".zip") and "win64" in name:
            zip_url = url
        elif name.endswith(".sha256"):
            sha256_url = url

    if not zip_url:
        return None

    return UpdateInfo(
        current=current_version,
        latest=latest,
        download_url=zip_url,
        sha256_url=sha256_url,
        release_url=release_url,
    )


def open_release_page(info: UpdateInfo) -> None:
    """Abre la página del release en el navegador por defecto."""
    webbrowser.open(info.release_url)


def download_release(
    info: UpdateInfo,
    dest_dir: Path | None = None,
    *,
    progress_callback: object = None,
) -> Path | None:
    """Descarga el ZIP del release y verifica el SHA-256.

    Args:
        info: Datos del release a descargar.
        dest_dir: Carpeta de destino. Si es ``None`` se usa un directorio
            temporal del sistema.
        progress_callback: Callable opcional ``(bytes_descargados, total)``
            llamado durante la descarga.

    Returns:
        Path del ZIP descargado, o ``None`` si falló la descarga o la
        verificación de integridad.
    """
    if dest_dir is None:
        dest_dir = Path(tempfile.mkdtemp(prefix="bankparser_update_"))
    dest_dir.mkdir(parents=True, exist_ok=True)

    zip_name = info.download_url.rsplit("/", 1)[-1]
    zip_path = dest_dir / zip_name

    try:
        with requests.get(info.download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with zip_path.open("wb") as fh:
                for chunk in r.iter_content(chunk_size=65536):
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if callable(progress_callback) and total:
                        progress_callback(downloaded, total)
    except Exception:
        if zip_path.exists():
            zip_path.unlink(missing_ok=True)
        return None

    # Verificar SHA-256 si está disponible
    if info.sha256_url:
        if not _verify_sha256(zip_path, info.sha256_url):
            zip_path.unlink(missing_ok=True)
            return None

    return zip_path


def _verify_sha256(zip_path: Path, sha256_url: str) -> bool:
    """Descarga el archivo .sha256 y compara contra el zip local."""
    try:
        resp = requests.get(sha256_url, timeout=10)
        resp.raise_for_status()
        # El archivo tiene formato: "HASH  filename" (dos espacios)
        expected_hash = resp.text.strip().split()[0].lower()
    except Exception:
        return True  # Si no se puede verificar, se acepta (fail-open)

    sha256 = hashlib.sha256()
    with zip_path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            sha256.update(block)
    actual_hash = sha256.hexdigest().lower()
    return actual_hash == expected_hash
