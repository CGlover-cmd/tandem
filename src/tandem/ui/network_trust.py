"""Is this network trusted? Windows' own Private/Public setting is Tandem's trust list.

The installer allows Tandem in from the local network on Private (and work-domain) networks
and blocks it on Public ones (ADR-0017, 1.1.1 addendum). Windows remembers that setting for
each network, so home can be trusted while a café stays blocked, and because a rule exists
for Tandem either way, Windows never asks "allow Python?". On a Public network the window says
so and offers to open Windows' network settings, where the user can mark it Private.

Reading the category needs no admin rights: `INetworkListManager` through ctypes (no extra
library). Network names are personal and are never read here, only the categories.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import uuid
from collections.abc import Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)

SETTINGS_URI = "ms-settings:network-status"
"""Windows Settings, Network: the connected network's Properties set Public or Private."""

CHECK_INTERVAL = 15.0
"""Seconds between checks: networks change when the PC moves or wakes."""

_CATEGORIES = {0: "public", 1: "private", 2: "domain"}


def read_categories() -> list[str] | None:  # pragma: no cover - needs Windows networking
    """The categories of the connected networks ("public", "private", "domain"), or None if
    they can't be read (not Windows, or the call failed)."""
    if sys.platform != "win32":
        return None
    try:
        return _read_categories()
    except OSError as exc:
        _LOGGER.debug("Couldn't read the network category (%s)", type(exc).__name__)
        return None


def _read_categories() -> list[str]:  # pragma: no cover - needs Windows networking
    import ctypes
    from ctypes import POINTER, byref, c_int, c_ulong, c_void_p

    class Guid(ctypes.Structure):
        _fields_ = [("data", ctypes.c_byte * 16)]

    def guid(text: str) -> Guid:
        value = Guid()
        ctypes.memmove(value.data, uuid.UUID(text).bytes_le, 16)
        return value

    def method(obj: c_void_p, index: int, *argtypes: Any) -> Callable[..., int]:
        table = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
        proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)
        function = proto(table[index])
        return lambda *args: function(obj, *args)

    def release(obj: c_void_p) -> None:
        if obj.value:
            table = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
            ctypes.WINFUNCTYPE(c_ulong, c_void_p)(table[2])(obj)

    ole32 = ctypes.OleDLL("ole32")
    ole32.CoInitializeEx(None, 0)  # multithreaded; harmless if this thread already has COM
    manager, networks = c_void_p(), c_void_p()
    categories: list[str] = []
    try:
        ole32.CoCreateInstance(
            byref(guid("DCB00C01-570F-4A9B-8D69-199FDBA5723B")),  # NetworkListManager
            None,
            1,  # in process
            byref(guid("DCB00000-570F-4A9B-8D69-199FDBA5723B")),  # INetworkListManager
            byref(manager),
        )
        # Vtable slots after IUnknown (3) and IDispatch (4): GetNetworks is 7; IEnumNetworks'
        # Next is 8; INetwork's GetCategory is 18.
        method(manager, 7, c_int, POINTER(c_void_p))(1, byref(networks))  # connected only
        while True:
            network, fetched = c_void_p(), c_ulong()
            method(networks, 8, c_ulong, POINTER(c_void_p), POINTER(c_ulong))(
                1, byref(network), byref(fetched)
            )
            if fetched.value == 0:
                break
            try:
                category = c_int()
                method(network, 18, POINTER(c_int))(byref(category))
                categories.append(_CATEGORIES.get(category.value, "unknown"))
            finally:
                release(network)
    finally:
        release(networks)
        release(manager)
    return categories


def untrusted(categories: list[str] | None) -> bool:
    """True when every connected network is Public, so the firewall keeps speakers out.
    Unknown, offline, or any trusted network: False (nothing to tell the user)."""
    return bool(categories) and all(c == "public" for c in categories or ())


def open_network_settings() -> None:  # pragma: no cover - opens Windows Settings
    if sys.platform == "win32":
        os.startfile(SETTINGS_URI)  # type: ignore[attr-defined]


class NetworkWatch:
    """Checks the network's category now and then and reports when "untrusted" changes."""

    def __init__(
        self,
        *,
        check: Callable[[], list[str] | None] = read_categories,
        open_settings: Callable[[], None] = open_network_settings,
        interval: float = CHECK_INTERVAL,
    ) -> None:
        self._check = check
        self._open_settings = open_settings
        self._interval = interval
        self.untrusted = False
        self._task: asyncio.Task[None] | None = None

    def start(self, on_change: Callable[[], None]) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run(on_change))

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def refresh(self) -> bool:
        """Check now. True if "untrusted" changed."""
        categories = await asyncio.to_thread(self._check)
        now = untrusted(categories)
        changed = now != self.untrusted
        self.untrusted = now
        return changed

    def open_settings(self) -> None:
        self._open_settings()

    async def _run(self, on_change: Callable[[], None]) -> None:
        while True:
            if await self.refresh():
                on_change()
            await asyncio.sleep(self._interval)
