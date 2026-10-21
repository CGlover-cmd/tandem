"""Shared test helpers. All device data here is invented (docs/PRIVACY.md, "Test data")."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tandem.engine.models import Device, DeviceKind, Service


def make_device(**overrides: Any) -> Device:
    fields: dict[str, Any] = {
        "id": "AA:BB:CC:00:00:01",
        "name": "Living Room Speaker",
        "address": "192.0.2.10",
        "kind": DeviceKind.HOMEPOD,
        "model": "HomePod mini",
        "services": frozenset({Service.AIRPLAY, Service.RAOP}),
    }
    fields.update(overrides)
    return Device(**fields)


class ManualSleep:
    """Stand-in for asyncio.sleep: records each delay and waits until the test releases it."""

    def __init__(self) -> None:
        self.delays: list[float] = []
        self._waiting: list[asyncio.Future[None]] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._waiting.append(future)
        await future

    def release(self) -> None:
        waiting, self._waiting = self._waiting, []
        for future in waiting:
            if not future.done():
                future.set_result(None)

    async def until(self, count: int) -> None:
        """Let the loop run until `count` sleeps have started."""
        for _ in range(1000):
            if len(self.delays) >= count:
                return
            await asyncio.sleep(0)
        raise AssertionError(f"expected {count} sleeps, saw {len(self.delays)}")


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def manual_sleep() -> ManualSleep:
    return ManualSleep()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def tandem_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "tandem-home"
    monkeypatch.setenv("TANDEM_HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def _reset_tandem_logging() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    yield
    for name in ("tandem", "pyatv"):
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        logger.propagate = True
        logger.setLevel(logging.NOTSET)
