"""Where Tandem keeps its files on this PC.

Everything lives under one folder: ``%LOCALAPPDATA%\\Tandem`` on Windows. Set the
``TANDEM_HOME`` environment variable to use another folder (tests, or a portable copy).
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Tandem"


def data_dir() -> Path:
    override = os.environ.get("TANDEM_HOME")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def settings_file() -> Path:
    return data_dir() / "settings.json"


def credentials_file() -> Path:
    return data_dir() / "credentials.bin"


def log_dir() -> Path:
    return data_dir() / "logs"
