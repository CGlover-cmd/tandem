"""Setup asks a running Tandem to quit before it replaces or removes its files (ADR-0017)."""

from __future__ import annotations

import asyncio
import re
import sys
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from tandem.ui import app
from tandem.ui.platform import QUIT_EVENT, SINGLE_INSTANCE, on_quit_request

ISS = Path(__file__).resolve().parents[2] / "packaging" / "tandem.iss"


def test_installer_looks_for_the_apps_own_names() -> None:
    script = ISS.read_text(encoding="utf-8")
    assert re.search(rf"QuitEventName\s*=\s*'{re.escape(QUIT_EVENT)}'", script)
    assert re.search(rf"InstanceMutexName\s*=\s*'{re.escape(SINGLE_INSTANCE)}'", script)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named events")
def test_setup_can_ask_tandem_to_quit() -> None:
    assert sys.platform == "win32"
    import ctypes
    from ctypes import wintypes

    name = r"Local\TandemTestQuit"
    asked = threading.Event()
    assert on_quit_request(asked.set, name)
    assert not asked.wait(0.2)  # nothing asked yet

    # What the installer does: open the event by name and set it.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.OpenEventW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.SetEvent.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    event_modify_state = 0x0002
    handle = kernel32.OpenEventW(event_modify_state, False, name)
    assert handle
    kernel32.SetEvent(handle)
    kernel32.CloseHandle(handle)
    assert asked.wait(5)


async def test_server_only_mode_quits_when_setup_asks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TANDEM_HOME", str(tmp_path))
    listeners: list[Callable[[], None]] = []
    listening = asyncio.Event()

    def listen(callback: Callable[[], None]) -> bool:  # called on the server's own loop
        listeners.append(callback)
        listening.set()
        return True

    monkeypatch.setattr(app, "on_quit_request", listen)
    running = asyncio.create_task(
        app._serve_only(app.parse_args(["--demo", "--no-window"]))  # pyright: ignore[reportPrivateUsage]
    )
    await asyncio.wait_for(listening.wait(), 30)
    threading.Thread(target=listeners[0]).start()  # setup's signal arrives on another thread
    assert await asyncio.wait_for(running, 30) == 0
