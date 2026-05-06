"""Auto-update vía GitHub Releases."""

from bank_parser.updater.github_updater import (
    UpdateInfo,
    check_for_update,
    download_release,
    open_release_page,
)

__all__ = ["UpdateInfo", "check_for_update", "download_release", "open_release_page"]
