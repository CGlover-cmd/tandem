from __future__ import annotations

import asyncio

import pytest

from tandem.ui.demo_backend import DemoBackend


async def _no_wait(_seconds: float) -> None:
    await asyncio.sleep(0)


@pytest.fixture
def backend() -> DemoBackend:
    """A demo backend whose delays take no time."""
    return DemoBackend(sleep=_no_wait)
