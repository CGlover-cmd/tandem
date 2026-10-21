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


def add_qt_dll_directory() -> None:
    """Let Qt's QML plugins find the Qt DLLs next to them.

    Python 3.8+ no longer searches PATH for DLL dependencies, so plugins such as
    QtQuick.Layouts fail with "The specified module could not be found" unless the PySide6
    folder is registered. Call before loading any QML.
    """
    if sys.platform != "win32":
        return
    import PySide6

    os.add_dll_directory(str(Path(PySide6.__file__).resolve().parent))
