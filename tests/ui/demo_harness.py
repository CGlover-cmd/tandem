"""Helpers for the window's tests on the demo (the real bridge and engine, invented devices)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from tandem.bridge import DemoBackend
from tandem.ui.controller import AppController


async def no_wait(_seconds: float) -> None:
    """The invented devices answer at once."""
    await asyncio.sleep(0)


async def short_waits(seconds: float) -> None:
    """The engine's retries happen at once; its discovery interval stays real (it never
    comes round during a test)."""
    await asyncio.sleep(0 if seconds < 20 else seconds)


def demo_backend(**options: object) -> DemoBackend:
    return DemoBackend(sleep=no_wait, engine_sleep=short_waits, **options)  # type: ignore[arg-type]


async def until(condition: Callable[[], bool], timeout: float = 3.0) -> None:
    """Wait, in real time, for something the engine does after a pause of its own (the
    music watcher waits a moment before saying nothing plays)."""
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not condition():
        if loop.time() > end:
            raise AssertionError("timed out waiting")
        await asyncio.sleep(0.02)


async def settle(controller: AppController | None = None) -> None:
    """Let commands, connections and the events they cause run to the end."""
    for _ in range(3):
        if controller is not None:
            await controller.runner.drain()
        for _ in range(100):
            await asyncio.sleep(0)
