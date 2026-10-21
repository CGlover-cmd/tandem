from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest

from conftest import FakeClock, ManualSleep, make_device
from tandem.engine.backoff import Backoff
from tandem.engine.discovery import Discovery
from tandem.engine.events import EventBus
from tandem.engine.models import Device
from tandem.engine.registry import DeviceAdded, DeviceEvent, DeviceLost, DeviceRegistry

SPEAKER = make_device(id="AA:BB:CC:00:00:01", name="Living Room Speaker")
TV = make_device(id="AA:BB:CC:00:00:02", name="Den TV")


class ScriptedScanner:
    """Returns each scripted result in turn (raising it if it's an exception)."""

    def __init__(self, *results: Sequence[Device] | Exception) -> None:
        self.results = list(results)
        self.timeouts: list[float] = []

    async def __call__(self, timeout: float) -> Sequence[Device]:
        self.timeouts.append(timeout)
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return result


def _setup(clock: FakeClock, scanner: ScriptedScanner, sleep: ManualSleep, **kwargs: object):
    bus = EventBus()
    events: list[DeviceEvent] = []
    bus.subscribe(DeviceEvent, events.append)
    registry = DeviceRegistry(bus, clock=clock)
    discovery = Discovery(registry, scanner, sleep=sleep, **kwargs)  # type: ignore[arg-type]
    return registry, discovery, events


async def test_scan_once_fills_the_registry(clock: FakeClock, manual_sleep: ManualSleep) -> None:
    scanner = ScriptedScanner([SPEAKER, TV])
    registry, discovery, events = _setup(clock, scanner, manual_sleep, scan_timeout=2.5)
    assert await discovery.scan_once() == [SPEAKER, TV]
    assert scanner.timeouts == [2.5]
    assert {d.id for d in registry.devices()} == {SPEAKER.id, TV.id}
    assert [type(e) for e in events] == [DeviceAdded, DeviceAdded]


async def test_device_is_lost_after_missing_scans(
    clock: FakeClock, manual_sleep: ManualSleep
) -> None:
    scanner = ScriptedScanner([SPEAKER, TV], [SPEAKER])
    registry, discovery, events = _setup(
        clock, scanner, manual_sleep, interval=10, scan_timeout=3, lost_after_scans=2
    )
    await discovery.scan_once()
    clock.now += 13 * 2  # exactly the limit: not lost yet
    await discovery.scan_once()
    assert TV.id in registry
    clock.now += 1
    await discovery.scan_once()
    assert TV.id not in registry
    assert events[-1] == DeviceLost(TV)


async def test_loop_scans_on_interval(clock: FakeClock, manual_sleep: ManualSleep) -> None:
    scanner = ScriptedScanner([SPEAKER])
    registry, discovery, _ = _setup(clock, scanner, manual_sleep, interval=7)
    discovery.start()
    discovery.start()  # idempotent
    assert discovery.running
    await manual_sleep.until(1)
    manual_sleep.release()
    await manual_sleep.until(2)
    assert manual_sleep.delays == [7, 7]
    assert len(scanner.timeouts) == 2
    assert SPEAKER.id in registry
    await discovery.stop()
    assert not discovery.running


async def test_failed_scans_back_off_and_keep_devices(
    clock: FakeClock, manual_sleep: ManualSleep
) -> None:
    scanner = ScriptedScanner([SPEAKER], OSError("no network"), OSError("no network"), [SPEAKER])
    registry, discovery, _ = _setup(
        clock,
        scanner,
        manual_sleep,
        interval=10,
        backoff=Backoff(initial=1, maximum=30, jitter=0),
    )
    discovery.start()
    for count in range(1, 4):
        await manual_sleep.until(count)
        clock.now += 100  # long enough to expire, if a failed scan expired anything
        manual_sleep.release()
    await manual_sleep.until(4)
    assert manual_sleep.delays == [10, 1, 2, 10]  # backoff resets after a good scan
    assert SPEAKER.id in registry
    await discovery.stop()


async def test_stop_without_start_is_harmless(clock: FakeClock, manual_sleep: ManualSleep) -> None:
    _, discovery, _ = _setup(clock, ScriptedScanner([]), manual_sleep)
    await discovery.stop()


async def test_stop_cancels_a_scan_in_progress(clock: FakeClock, manual_sleep: ManualSleep) -> None:
    started = asyncio.Event()

    async def slow_scan(_timeout: float) -> Sequence[Device]:
        started.set()
        await asyncio.Event().wait()
        return []

    registry = DeviceRegistry(EventBus(), clock=clock)
    discovery = Discovery(registry, slow_scan, sleep=manual_sleep)
    discovery.start()
    await started.wait()
    await discovery.stop()
    assert not discovery.running


@pytest.mark.parametrize("kwargs", [{"interval": 0}, {"scan_timeout": -1}, {"lost_after_scans": 0}])
def test_invalid_arguments(kwargs: dict[str, float]) -> None:
    registry = DeviceRegistry(EventBus())
    with pytest.raises(ValueError, match="positive"):
        Discovery(registry, ScriptedScanner([]), **kwargs)  # type: ignore[arg-type]
