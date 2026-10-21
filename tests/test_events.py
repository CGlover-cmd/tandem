from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from tandem.engine.events import Event, EventBus


@dataclass(frozen=True, slots=True)
class Ping(Event):
    n: int


@dataclass(frozen=True, slots=True)
class LoudPing(Ping):
    pass


def test_publish_reaches_subscribers_in_order() -> None:
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(Ping, lambda e: seen.append(f"a{e.n}"))
    bus.subscribe(Ping, lambda e: seen.append(f"b{e.n}"))
    bus.publish(Ping(1))
    assert seen == ["a1", "b1"]


def test_base_class_subscribers_receive_subclasses() -> None:
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe(Event, seen.append)
    bus.subscribe(Ping, seen.append)
    bus.publish(LoudPing(2))
    assert seen == [LoudPing(2), LoudPing(2)]


def test_subclass_subscribers_ignore_base_events() -> None:
    bus = EventBus()
    seen: list[Ping] = []
    bus.subscribe(LoudPing, seen.append)
    bus.publish(Ping(1))
    assert seen == []


def test_unsubscribe_stops_delivery_and_is_idempotent() -> None:
    bus = EventBus()
    seen: list[Ping] = []
    unsubscribe = bus.subscribe(Ping, seen.append)
    unsubscribe()
    unsubscribe()
    bus.publish(Ping(1))
    assert seen == []


def test_failing_handler_does_not_block_others(caplog: pytest.LogCaptureFixture) -> None:
    bus = EventBus()
    seen: list[Ping] = []

    def broken(_event: Ping) -> None:
        raise RuntimeError("boom")

    bus.subscribe(Ping, broken)
    bus.subscribe(Ping, seen.append)
    bus.publish(Ping(1))
    assert seen == [Ping(1)]
    assert "Event handler failed for Ping" in caplog.text


def test_handler_may_unsubscribe_during_publish() -> None:
    bus = EventBus()
    seen: list[int] = []

    def once(event: Ping) -> None:
        seen.append(event.n)
        unsubscribe()

    unsubscribe = bus.subscribe(Ping, once)
    bus.publish(Ping(1))
    bus.publish(Ping(2))
    assert seen == [1]


async def test_listen_collects_events_while_open() -> None:
    bus = EventBus()
    async with bus.listen(Ping) as queue:
        bus.publish(Ping(1))
        assert await queue.get() == Ping(1)
    bus.publish(Ping(2))
    assert queue.empty()


async def test_wait_for_matches_predicate() -> None:
    bus = EventBus()
    waiter = asyncio.create_task(bus.wait_for(Ping, lambda e: e.n == 3, timeout=1))
    await asyncio.sleep(0)
    for n in (1, 2, 3, 4):
        bus.publish(Ping(n))
    assert await waiter == Ping(3)


async def test_wait_for_times_out_and_unsubscribes() -> None:
    bus = EventBus()
    with pytest.raises(TimeoutError):
        await bus.wait_for(Ping, timeout=0.01)
    bus.publish(Ping(1))  # no stale handler left behind to trip over a finished future
