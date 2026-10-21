from __future__ import annotations

import asyncio

import pytest

from conftest import ManualSleep
from tandem.engine.backoff import Backoff
from tandem.engine.events import EventBus
from tandem.engine.session import (
    ConnectionFailedError,
    ConnectionSession,
    ConnectionState,
    ConnectionStateChanged,
    Link,
    LostCallback,
)

DEVICE_ID = "AA:BB:CC:00:00:01"
NO_JITTER = Backoff(initial=1.0, maximum=8.0, factor=2.0, jitter=0.0)
S = ConnectionState


class FakeLink:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeConnector:
    """Fails with each scripted exception in turn, then hands out FakeLinks."""

    def __init__(self, *failures: BaseException) -> None:
        self.failures = list(failures)
        self.links: list[FakeLink] = []
        self.on_lost: LostCallback | None = None
        self.calls = 0

    async def __call__(self, on_lost: LostCallback) -> Link:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        self.on_lost = on_lost
        link = FakeLink()
        self.links.append(link)
        return link


def _session(connector: FakeConnector, sleep: ManualSleep, **kwargs: object):
    bus = EventBus()
    changes: list[ConnectionStateChanged] = []
    bus.subscribe(ConnectionStateChanged, changes.append)
    session = ConnectionSession(
        DEVICE_ID,
        connector,
        bus,
        backoff=NO_JITTER,
        sleep=sleep,
        **kwargs,  # type: ignore[arg-type]
    )
    return session, changes


async def test_connects(manual_sleep: ManualSleep) -> None:
    connector = FakeConnector()
    session, changes = _session(connector, manual_sleep)
    session.start()
    link = await session.wait_connected(timeout=1)
    assert link is connector.links[0]
    assert session.link is link
    assert session.state is S.CONNECTED
    assert [(c.previous, c.state) for c in changes] == [
        (S.DISCONNECTED, S.CONNECTING),
        (S.CONNECTING, S.CONNECTED),
    ]
    assert await session.wait_connected() is link  # already connected: returns at once
    await session.close()


async def test_retries_with_backoff_until_connected(manual_sleep: ManualSleep) -> None:
    connector = FakeConnector(OSError("refused"), TimeoutError())
    session, changes = _session(connector, manual_sleep)
    session.start()
    await manual_sleep.until(1)
    manual_sleep.release()
    await manual_sleep.until(2)
    manual_sleep.release()
    await session.wait_connected(timeout=1)
    assert manual_sleep.delays == [1.0, 2.0]
    waiting = [c for c in changes if c.state is S.WAITING]
    assert [(c.attempt, c.retry_in, c.reason) for c in waiting] == [
        (1, 1.0, "OSError"),
        (2, 2.0, "TimeoutError"),
    ]
    await session.close()


async def test_gives_up_after_max_attempts(manual_sleep: ManualSleep) -> None:
    connector = FakeConnector(OSError(), OSError(), OSError())
    session, changes = _session(connector, manual_sleep, max_attempts=2)
    session.start()
    await manual_sleep.until(1)
    waiter = asyncio.create_task(session.wait_connected(timeout=1))
    await asyncio.sleep(0)
    manual_sleep.release()
    with pytest.raises(ConnectionFailedError, match="failed"):
        await waiter
    assert session.state is S.FAILED
    assert changes[-1].attempt == 2
    assert connector.calls == 2
    with pytest.raises(ConnectionFailedError):
        await session.wait_connected()


async def test_reconnects_after_a_drop(manual_sleep: ManualSleep) -> None:
    connector = FakeConnector()
    session, changes = _session(connector, manual_sleep)
    session.start()
    first = await session.wait_connected(timeout=1)
    assert connector.on_lost is not None
    connector.on_lost(ConnectionResetError())
    await manual_sleep.until(1)
    assert first.closed  # type: ignore[attr-defined]
    assert session.link is None
    assert changes[-1].state is S.WAITING
    assert changes[-1].reason == "ConnectionResetError"
    manual_sleep.release()
    second = await session.wait_connected(timeout=1)
    assert second is not first
    await session.close()


async def test_clean_close_from_the_device_also_reconnects(manual_sleep: ManualSleep) -> None:
    connector = FakeConnector()
    session, changes = _session(connector, manual_sleep)
    session.start()
    await session.wait_connected(timeout=1)
    assert connector.on_lost is not None
    connector.on_lost(None)
    await manual_sleep.until(1)
    assert changes[-1].reason == "ConnectionClosed"
    await session.close()


async def test_close_while_connected(manual_sleep: ManualSleep) -> None:
    connector = FakeConnector()
    session, changes = _session(connector, manual_sleep)
    session.start()
    link = await session.wait_connected(timeout=1)
    await session.close()
    assert link.closed  # type: ignore[attr-defined]
    assert session.state is S.DISCONNECTED
    assert session.link is None
    assert changes[-1].state is S.DISCONNECTED
    assert connector.calls == 1


async def test_close_while_waiting_to_retry(manual_sleep: ManualSleep) -> None:
    session, _ = _session(FakeConnector(OSError()), manual_sleep)
    session.start()
    await manual_sleep.until(1)
    await session.close()
    assert session.state is S.DISCONNECTED


async def test_close_wakes_a_waiter(manual_sleep: ManualSleep) -> None:
    session, _ = _session(FakeConnector(OSError()), manual_sleep)
    session.start()
    await manual_sleep.until(1)
    waiter = asyncio.create_task(session.wait_connected(timeout=1))
    await asyncio.sleep(0)
    await session.close()
    with pytest.raises(ConnectionFailedError, match="disconnected"):
        await waiter


async def test_connect_timeout_counts_as_a_failure(manual_sleep: ManualSleep) -> None:
    async def hangs(_on_lost: LostCallback) -> Link:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    bus = EventBus()
    session = ConnectionSession(
        DEVICE_ID, hangs, bus, connect_timeout=0.01, max_attempts=1, sleep=manual_sleep
    )
    session.start()
    with pytest.raises(ConnectionFailedError):
        await session.wait_connected(timeout=1)


async def test_wait_connected_before_start_fails_fast(manual_sleep: ManualSleep) -> None:
    session, _ = _session(FakeConnector(), manual_sleep)
    with pytest.raises(ConnectionFailedError):
        await session.wait_connected()


async def test_start_after_failure_tries_again(manual_sleep: ManualSleep) -> None:
    connector = FakeConnector(OSError())
    session, _ = _session(connector, manual_sleep, max_attempts=1)
    session.start()
    with pytest.raises(ConnectionFailedError):
        await session.wait_connected(timeout=1)
    session.start()
    await session.wait_connected(timeout=1)
    await session.close()


async def test_close_link_errors_are_swallowed(manual_sleep: ManualSleep) -> None:
    class BrokenLink:
        async def close(self) -> None:
            raise OSError("already gone")

    async def connect(_on_lost: LostCallback) -> Link:
        return BrokenLink()

    session = ConnectionSession(DEVICE_ID, connect, EventBus(), sleep=manual_sleep)
    session.start()
    await session.wait_connected(timeout=1)
    await session.close()
    assert session.state is S.DISCONNECTED


async def test_supervisor_bug_is_reported_as_failed(manual_sleep: ManualSleep) -> None:
    class BrokenBackoff(Backoff):
        def delay(self, attempt: int, rng: object = None) -> float:  # type: ignore[override]
            raise RuntimeError("bug")

    bus = EventBus()
    session = ConnectionSession(
        DEVICE_ID, FakeConnector(OSError()), bus, backoff=BrokenBackoff(), sleep=manual_sleep
    )
    session.start()
    with pytest.raises(ConnectionFailedError):
        await session.wait_connected(timeout=1)
    assert session.state is S.FAILED


def test_max_attempts_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        ConnectionSession(DEVICE_ID, FakeConnector(), EventBus(), max_attempts=0)
