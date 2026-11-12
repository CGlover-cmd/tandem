"""Notice when the PC's network changes, so Tandem reacts at once instead of on its next scan.

Moving to another Wi-Fi, plugging in a cable, a VPN coming up, or waking from sleep all leave
speaker connections dead and the device list stale. Waiting for the next discovery scan (10 s)
and each connection's backoff (up to 30 s) makes Tandem look broken for a while. AirParrot
fixed the same thing ("reliability when changing networks", 2.7.0).

The check is cheap and needs no admin rights: the PC's own IPv4 addresses, read every few
seconds. A gap much longer than the interval means the PC slept, which counts as a change too.
Addresses are private: they are compared, never logged.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import time
from collections.abc import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)

CHECK_INTERVAL = 3.0
"""Seconds between checks."""

SLEEP_GAP = 20.0
"""A check this much later than planned means the PC was asleep."""

_PROBE = "192.0.2.1"  # TEST-NET-1: connecting a UDP socket to it sends nothing


def read_addresses() -> frozenset[str]:
    """The PC's IPv4 addresses (the one with the default route, plus those its name resolves
    to). Empty when offline."""
    found: set[str] = set()
    with contextlib.suppress(OSError), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((_PROBE, 9))
        found.add(str(s.getsockname()[0]))
    with contextlib.suppress(OSError):
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(str(info[4][0]))
    return frozenset(a for a in found if not a.startswith("127.") and a != "0.0.0.0")


class NetworkWatch:
    """Calls `on_change` when the PC's addresses change or it wakes from sleep."""

    def __init__(
        self,
        *,
        read: Callable[[], frozenset[str]] = read_addresses,
        interval: float = CHECK_INTERVAL,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._read = read
        self._interval = interval
        self._clock = clock
        self._sleep = sleep
        self._task: asyncio.Task[None] | None = None
        self.addresses: frozenset[str] | None = None
        """The addresses at the last check (private)."""
        self.changes = 0
        """How many changes were noticed (for tests and diagnostics)."""

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, on_change: Callable[[], Awaitable[None]]) -> None:
        if not self.running:
            self._task = asyncio.get_running_loop().create_task(
                self._run(on_change), name="network-watch"
            )

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def check(self) -> bool:
        """Read the addresses now. True if they changed since the last check."""
        now = await asyncio.to_thread(self._read)
        before, self.addresses = self.addresses, now
        return before is not None and now != before

    async def _run(self, on_change: Callable[[], Awaitable[None]]) -> None:
        await self.check()
        last = self._clock()
        while True:
            await self._sleep(self._interval)
            now = self._clock()
            woke = now - last > self._interval + SLEEP_GAP
            last = now
            try:
                changed = await self.check()
            except Exception as exc:
                _LOGGER.debug("Couldn't read the network (%s)", type(exc).__name__)
                continue
            if changed or woke:
                self.changes += 1
                _LOGGER.info("The network changed%s; checking speakers", " (woke)" if woke else "")
                try:
                    await on_change()
                except Exception:
                    _LOGGER.exception("Reacting to a network change failed")
