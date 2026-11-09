from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import suppress

import pytest
from demo_harness import demo_backend

from tandem.bridge import DemoBackend


@pytest.fixture
async def backend() -> AsyncIterator[DemoBackend]:
    """The real bridge and engine on the demo's invented devices, without waits."""
    backend = demo_backend()
    yield backend
    with suppress(Exception):
        await backend.stop()
