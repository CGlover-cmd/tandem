"""Small Windows integration helpers for the UI."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

_SPI_GETCLIENTAREAANIMATION = 0x1042


def reduce_motion() -> bool:
    """True when Windows "Animation effects" is off (Settings > Accessibility > Visual effects)."""
    if sys.platform != "win32":
        return False
    enabled = ctypes.c_int(1)
    ok = ctypes.windll.user32.SystemParametersInfoW(
        _SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0
    )
    return bool(ok) and not enabled.value


def store_country() -> str:
    """Two-letter region for App Store lookups, from the Windows display locale (e.g.
    "en-GB" gives "gb"). Falls back to "us"."""
    if sys.platform == "win32":
        buffer = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, 85):
            region = buffer.value.split("-")[-1]
            if len(region) == 2 and region.isalpha():
                return region.lower()
    return "us"


def ui_data_dir() -> Path:
    """The UI's folder for its own small files (same rules as `tandem.engine.paths`)."""
    override = os.environ.get("TANDEM_HOME")
    if override:
        return Path(override) / "ui"
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "Tandem" / "ui"
    return Path.home() / ".tandem" / "ui"
