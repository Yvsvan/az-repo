"""Tests para github_updater — todo con requests mockeado, sin red real."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from bank_parser.updater.github_updater import (
    UpdateInfo,
    check_for_update,
    parse_latest_version,
)

# ---------------------------------------------------------------------------
# fixture: respuesta GitHub API bien formada
# ---------------------------------------------------------------------------

_REPO = "ivan-aguilera/az-repo"
_CURRENT = "0.0.1"
_LATEST_TAG = "v1.2.3"
_LATEST_VER = "1.2.3"

_GOOD_RESPONSE = {
    "tag_name": _LATEST_TAG,
    "html_url": f"https://github.com/{_REPO}/releases/tag/{_LATEST_TAG}",
    "assets": [
        {
            "name": f"BankParser-{_LATEST_TAG}-win64.zip",
            "browser_download_url": f"https://github.com/{_REPO}/releases/download/{_LATEST_TAG}/BankParser-{_LATEST_TAG}-win64.zip",
        },
        {
            "name": f"BankParser-{_LATEST_TAG}-win64.zip.sha256",
            "browser_download_url": f"https://github.com/{_REPO}/releases/download/{_LATEST_TAG}/BankParser-{_LATEST_TAG}-win64.zip.sha256",
        },
    ],
}


def _mock_response(payload: dict, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    r.raise_for_status = MagicMock(
        side_effect=None if status < 400 else Exception(f"HTTP {status}")
    )
    return r


# ---------------------------------------------------------------------------
# parse_latest_version
# ---------------------------------------------------------------------------


def test_parse_strips_v_prefix() -> None:
    assert parse_latest_version("v1.2.3") == "1.2.3"


def test_parse_no_prefix() -> None:
    assert parse_latest_version("2.0.0") == "2.0.0"


def test_parse_empty_returns_none() -> None:
    assert parse_latest_version("") is None


def test_parse_garbage_returns_none() -> None:
    assert parse_latest_version("not-a-version") is None


# ---------------------------------------------------------------------------
# check_for_update — update disponible
# ---------------------------------------------------------------------------


def test_returns_update_info_when_newer() -> None:
    with patch("bank_parser.updater.github_updater.requests.get") as mock_get:
        mock_get.return_value = _mock_response(_GOOD_RESPONSE)
        info = check_for_update(_REPO, _CURRENT)
    assert info is not None
    assert info.latest == _LATEST_VER
    assert info.current == _CURRENT
    assert info.download_url.endswith(".zip")


def test_update_info_has_sha256_url() -> None:
    with patch("bank_parser.updater.github_updater.requests.get") as mock_get:
        mock_get.return_value = _mock_response(_GOOD_RESPONSE)
        info = check_for_update(_REPO, _CURRENT)
    assert info is not None
    assert info.sha256_url is not None
    assert info.sha256_url.endswith(".sha256")


def test_update_info_has_release_url() -> None:
    with patch("bank_parser.updater.github_updater.requests.get") as mock_get:
        mock_get.return_value = _mock_response(_GOOD_RESPONSE)
        info = check_for_update(_REPO, _CURRENT)
    assert info is not None
    assert info.release_url.startswith("https://")


# ---------------------------------------------------------------------------
# check_for_update — sin update
# ---------------------------------------------------------------------------


def test_returns_none_when_same_version() -> None:
    payload = dict(_GOOD_RESPONSE, tag_name="v0.0.1")
    with patch("bank_parser.updater.github_updater.requests.get") as mock_get:
        mock_get.return_value = _mock_response(payload)
        assert check_for_update(_REPO, "0.0.1") is None


def test_returns_none_when_older_tag() -> None:
    payload = dict(_GOOD_RESPONSE, tag_name="v0.0.0")
    with patch("bank_parser.updater.github_updater.requests.get") as mock_get:
        mock_get.return_value = _mock_response(payload)
        assert check_for_update(_REPO, "0.0.1") is None


# ---------------------------------------------------------------------------
# check_for_update — errores de red y respuestas malformadas
# ---------------------------------------------------------------------------


def test_returns_none_on_connection_error() -> None:
    with patch("bank_parser.updater.github_updater.requests.get") as mock_get:
        mock_get.side_effect = ConnectionError("sin red")
        assert check_for_update(_REPO, _CURRENT) is None


def test_returns_none_on_timeout() -> None:
    import requests as req

    with patch("bank_parser.updater.github_updater.requests.get") as mock_get:
        mock_get.side_effect = req.Timeout("timeout")
        assert check_for_update(_REPO, _CURRENT) is None


def test_returns_none_on_http_error() -> None:
    with patch("bank_parser.updater.github_updater.requests.get") as mock_get:
        mock_get.return_value = _mock_response({}, status=403)
        assert check_for_update(_REPO, _CURRENT) is None


def test_returns_none_on_invalid_json() -> None:
    with patch("bank_parser.updater.github_updater.requests.get") as mock_get:
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json.side_effect = json.JSONDecodeError("bad", "", 0)
        mock_get.return_value = r
        assert check_for_update(_REPO, _CURRENT) is None


def test_returns_none_when_tag_missing() -> None:
    with patch("bank_parser.updater.github_updater.requests.get") as mock_get:
        mock_get.return_value = _mock_response({"assets": []})
        assert check_for_update(_REPO, _CURRENT) is None


def test_returns_none_when_no_zip_asset() -> None:
    payload = dict(_GOOD_RESPONSE, assets=[])
    with patch("bank_parser.updater.github_updater.requests.get") as mock_get:
        mock_get.return_value = _mock_response(payload)
        assert check_for_update(_REPO, _CURRENT) is None


def test_returns_none_when_tag_is_garbage() -> None:
    payload = dict(_GOOD_RESPONSE, tag_name="not-semver")
    with patch("bank_parser.updater.github_updater.requests.get") as mock_get:
        mock_get.return_value = _mock_response(payload)
        assert check_for_update(_REPO, _CURRENT) is None


# ---------------------------------------------------------------------------
# UpdateInfo dataclass
# ---------------------------------------------------------------------------


def test_update_info_is_newer_true() -> None:
    info = UpdateInfo(
        current="0.0.1",
        latest="1.0.0",
        download_url="https://example.com/file.zip",
        sha256_url=None,
        release_url="https://github.com/r/releases/tag/v1.0.0",
    )
    assert info.is_newer


def test_update_info_is_newer_false_same() -> None:
    info = UpdateInfo(
        current="1.0.0",
        latest="1.0.0",
        download_url="https://example.com/file.zip",
        sha256_url=None,
        release_url="https://github.com/r/releases/tag/v1.0.0",
    )
    assert not info.is_newer


def test_update_info_display_message() -> None:
    info = UpdateInfo(
        current="0.0.1",
        latest="1.2.3",
        download_url="https://x.com/f.zip",
        sha256_url=None,
        release_url="https://github.com/r/releases/tag/v1.2.3",
    )
    msg = info.display_message
    assert "1.2.3" in msg
    assert "0.0.1" in msg
