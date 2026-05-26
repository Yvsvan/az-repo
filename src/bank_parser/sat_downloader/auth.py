"""Carga de e.firma y gestión de contraseñas con Windows Credential Manager."""

from __future__ import annotations

from pathlib import Path

import keyring
import keyring.errors
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from bank_parser.sat_downloader.schema import SatCredential

_KEYRING_SERVICE = "az-repo-sat"


def load_credential(
    cer_path: Path, key_path: Path, password: str, alias: str = ""
) -> SatCredential:
    """Carga un par .cer/.key, valida la contraseña y retorna un SatCredential listo."""
    cert_der = cer_path.read_bytes()
    cert = x509.load_der_x509_certificate(cert_der)
    rfc = _extract_rfc(cert)

    key_bytes = key_path.read_bytes()
    private_key = _load_private_key(key_bytes, password)

    return SatCredential(
        rfc=rfc,
        alias=alias or rfc,
        cer_path=cer_path,
        key_path=key_path,
        private_key=private_key,
        cert_der=cert_der,
    )


def _load_private_key(key_bytes: bytes, password: str):
    """Intenta cargar una llave privada SAT probando varias estrategias.

    Las llaves e.firma del SAT son PKCS#8 DER cifradas (3DES/SHA-1).
    Se intenta UTF-8 primero, luego Latin-1 (por contraseñas con ñ/acentos).
    """
    errors: list[str] = []

    # Estrategia 1 — DER PKCS#8, contraseña UTF-8 (formato estándar SAT)
    try:
        return serialization.load_der_private_key(key_bytes, password=password.encode("utf-8"))
    except Exception as exc:
        errors.append(f"DER/UTF-8: {exc}")

    # Estrategia 2 — DER PKCS#8, contraseña Latin-1 (contraseñas con ñ/acentos)
    try:
        return serialization.load_der_private_key(key_bytes, password=password.encode("latin-1"))
    except Exception as exc:
        errors.append(f"DER/Latin-1: {exc}")

    # Estrategia 3 — PEM PKCS#8 (exportación alternativa, poco común)
    try:
        return serialization.load_pem_private_key(key_bytes, password=password.encode("utf-8"))
    except Exception as exc:
        errors.append(f"PEM/UTF-8: {exc}")

    # Nada funcionó — armar mensaje claro para el usuario
    first_err = errors[0] if errors else "desconocido"
    _wrong_pwd_signals = (
        "BadDecryptionError",
        "InvalidTag",
        "Mac verify",
        "Incorrect password",
        "could not decrypt",
        "bad decrypt",
    )
    if any(s.lower() in first_err.lower() for s in _wrong_pwd_signals):
        hint = "La contraseña es incorrecta."
    elif "unsupported" in first_err.lower():
        hint = "Algoritmo de cifrado no soportado. Verifica que el archivo .key sea de e.firma SAT."
    else:
        hint = "Verifica que el archivo .key sea de e.firma SAT y que la contraseña sea correcta."

    raise ValueError(f"{hint}\n\nDetalle técnico: {first_err}")


def _extract_rfc(cert: x509.Certificate) -> str:
    """Extrae el RFC del Subject del certificado SAT."""
    # OID 2.5.4.45 (UniqueIdentifier) contiene "RFC / CURP / ..."
    try:
        uid_attrs = cert.subject.get_attributes_for_oid(x509.NameOID.X500_UNIQUE_IDENTIFIER)
        if uid_attrs:
            raw = uid_attrs[0].value
            return raw.split("/")[0].strip().upper()
    except Exception:
        pass
    # Fallback: Common Name (nombre / RFC)
    try:
        cn_attrs = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
        if cn_attrs:
            return cn_attrs[0].value.strip().upper()
    except Exception:
        pass
    raise ValueError(
        "No se pudo extraer el RFC del certificado. Verifica que sea un certificado SAT válido."
    )


# ---------------------------------------------------------------------------
# Keyring (Windows Credential Manager)
# ---------------------------------------------------------------------------


def save_password(rfc: str, password: str) -> None:
    keyring.set_password(_KEYRING_SERVICE, rfc.upper(), password)


def load_password(rfc: str) -> str | None:
    return keyring.get_password(_KEYRING_SERVICE, rfc.upper())


def delete_password(rfc: str) -> None:
    try:
        keyring.delete_password(_KEYRING_SERVICE, rfc.upper())
    except keyring.errors.PasswordDeleteError:
        pass
