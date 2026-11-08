"""Small Windows integration helpers for the UI."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
from collections.abc import Callable
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


_ERROR_ALREADY_EXISTS = 183
_held: list[int] = []


def claim_single_instance(name: str = r"Local\TandemApp") -> bool:
    """True if this is the only Tandem window running (for this Windows user).

    A second copy would open its own connection to the Apple TV, which makes the TV drop the
    first one, and both would want the Home bridge's port. The mutex is held until exit.
    """
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        return True  # can't tell: don't block the user
    if kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _held.append(handle)
    return True


def reveal_in_explorer(path: Path) -> None:  # pragma: no cover - opens a window
    """Open File Explorer with `path` selected."""
    if sys.platform == "win32":
        subprocess.Popen(["explorer.exe", f"/select,{path}"])


_MOD_ALT, _MOD_CONTROL, _MOD_NOREPEAT = 0x1, 0x2, 0x4000
_VK_K = 0x4B
_WM_HOTKEY, _WM_QUIT = 0x0312, 0x0012


class GlobalHotkey:  # pragma: no cover - needs a desktop; checked by hand
    """Ctrl+Alt+K anywhere in Windows calls `on_press` (on this class's own thread).

    RegisterHotKey delivers to the thread that registered it, so the thread owns a message
    loop. If another app already holds the combination, Tandem simply goes without it.
    """

    def __init__(self, on_press: Callable[[], None]) -> None:
        self._on_press = on_press
        self._thread_id = 0
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if sys.platform != "win32" or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="tandem-hotkey", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)

    def _run(self) -> None:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, _MOD_CONTROL | _MOD_ALT | _MOD_NOREPEAT, _VK_K):
            return
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == _WM_HOTKEY:
                    self._on_press()
        finally:
            user32.UnregisterHotKey(None, 1)
