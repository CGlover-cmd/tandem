from __future__ import annotations

from conftest import FakeClock, make_device
from tandem.engine.events import EventBus
from tandem.engine.models import Service
from tandem.engine.redact import Redactor
from tandem.engine.registry import (
    DeviceAdded,
    DeviceEvent,
    DeviceLost,
    DeviceRegistry,
    DeviceUpdated,
)


def _registry(clock: FakeClock, redactor: Redactor | None = None):
    bus = EventBus()
    events: list[DeviceEvent] = []
    bus.subscribe(DeviceEvent, events.append)
    return DeviceRegistry(bus, redactor, clock), events


def test_new_device_is_added(clock: FakeClock) -> None:
    registry, events = _registry(clock)
    device = make_device()
    registry.upsert(device)
    assert events == [DeviceAdded(device)]
    assert registry.get(device.id) == device
    assert device.id in registry
    assert len(registry) == 1
    assert registry.last_seen(device.id) == clock.now


def test_seeing_an_unchanged_device_publishes_nothing(clock: FakeClock) -> None:
    registry, events = _registry(clock)
    registry.upsert(make_device())
    clock.now += 5
    registry.upsert(make_device())
    assert len(events) == 1
    assert registry.last_seen(make_device().id) == clock.now


def test_changed_device_is_updated(clock: FakeClock) -> None:
    registry, events = _registry(clock)
    old = make_device()
    new = make_device(address="192.0.2.11", services=frozenset({Service.RAOP}))
    registry.upsert(old)
    registry.upsert(new)
    assert events[-1] == DeviceUpdated(new, old)


def test_stale_devices_expire(clock: FakeClock) -> None:
    registry, events = _registry(clock)
    old = make_device(id="AA:BB:CC:00:00:01")
    fresh = make_device(id="AA:BB:CC:00:00:02", name="Porch Speaker")
    registry.upsert(old)
    clock.now += 20
    registry.upsert(fresh)
    clock.now += 15
    assert registry.expire(max_age=30) == [old]
    assert events[-1] == DeviceLost(old)
    assert registry.devices() == [fresh]
    assert registry.last_seen(old.id) is None


def test_devices_are_sorted_by_name(clock: FakeClock) -> None:
    registry, _ = _registry(clock)
    registry.upsert(make_device(id="AA:BB:CC:00:00:01", name="living room"))
    registry.upsert(make_device(id="AA:BB:CC:00:00:02", name="Porch"))
    assert [d.name for d in registry.devices()] == ["living room", "Porch"]


def test_names_and_ids_are_registered_for_redaction(clock: FakeClock) -> None:
    redactor = Redactor()
    registry, _ = _registry(clock, redactor)
    registry.upsert(make_device(id="device-1234", name="Living Room Speaker"))
    assert redactor.redact("Living Room Speaker (device-1234)") == "<device-1> (<id-1>)"
