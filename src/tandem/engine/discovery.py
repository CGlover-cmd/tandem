"""Continuous discovery: scan the network on an interval and keep the registry current."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress

from tandem.engine.backoff import Backoff
from tandem.engine.models import Device
from tandem.engine.registry import DeviceRegistry

_LOGGER = logging.getLogger(__name__)

Scanner = Callable[[float], Awaitable[Sequence[Device]]]
"""Scan the network for `timeout` seconds and return the devices found."""

Sleep = Callable[[float], Awaitable[None]]


class Discovery:
    """Runs `scanner` repeatedly and feeds the results into the registry.

    A device is reported lost once it has been missing for `lost_after_scans` scan cycles.
    A failing scan is retried with backoff and drops no devices.
    """

    def __init__(
        self,
        registry: DeviceRegistry,
        scanner: Scanner,
        *,
        interval: float = 10.0,
        scan_timeout: float = 3.0,
        lost_after_scans: int = 3,
        backoff: Backoff | None = None,
        sleep: Sleep = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        if interval <= 0 or scan_timeout <= 0 or lost_after_scans < 1:
            raise ValueError("interval, scan_timeout and lost_after_scans must be positive")
        self._registry = registry
        self._scanner = scanner
        self._interval = interval
        self._scan_timeout = scan_timeout
        self._max_age = lost_after_scans * (interval + scan_timeout)
        self._backoff = backoff or Backoff(initial=1.0, maximum=interval * 3)
        self._sleep = sleep
        self._rng = rng
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def scan_once(self) -> list[Device]:
        """Scan once, update the registry and expire stale devices. Scan errors propagate."""
        found = list(await self._scanner(self._scan_timeout))
        for device in found:
            self._registry.upsert(device)
        self._registry.expire(self._max_age)
        return found

    def start(self) -> None:
        if not self.running:
            self._task = asyncio.get_running_loop().create_task(self._run(), name="discovery")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _run(self) -> None:
        failures = 0
        while True:
            try:
                found = await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                delay = self._backoff.delay(failures, self._rng)
                failures += 1
                _LOGGER.warning(
                    "Discovery scan failed (%s); retrying in %.1f s", type(exc).__name__, delay
                )
                await self._sleep(delay)
                continue
            failures = 0
            _LOGGER.debug("Discovery scan found %d device(s)", len(found))
            await self._sleep(self._interval)
