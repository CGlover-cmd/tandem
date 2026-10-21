"""The set of devices currently visible on the network."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from tandem.engine.events import Event, EventBus
from tandem.engine.models import Device
from tandem.engine.redact import Redactor


@dataclass(frozen=True, slots=True)
class DeviceEvent(Event):
    device: Device


@dataclass(frozen=True, slots=True)
class DeviceAdded(DeviceEvent):
    """A device appeared (for the first time, or again after being lost)."""


@dataclass(frozen=True, slots=True)
class DeviceUpdated(DeviceEvent):
    """A known device changed name, address, model or services."""

    previous: Device


@dataclass(frozen=True, slots=True)
class DeviceLost(DeviceEvent):
    """A device hasn't been seen for longer than the discovery timeout."""


class DeviceRegistry:
    """Devices keyed by id, with the time each was last seen.

    Every device's name and id are registered with the redactor as soon as they are seen,
    so nothing logged afterwards can leak them.
    """

    def __init__(
        self,
        bus: EventBus,
        redactor: Redactor | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._bus = bus
        self._redactor = redactor
        self._clock = clock
        self._devices: dict[str, Device] = {}
        self._last_seen: dict[str, float] = {}

    def __len__(self) -> int:
        return len(self._devices)

    def __contains__(self, device_id: object) -> bool:
        return device_id in self._devices

    def get(self, device_id: str) -> Device | None:
        return self._devices.get(device_id)

    def devices(self) -> list[Device]:
        """All visible devices, sorted by name for stable display."""
        return sorted(self._devices.values(), key=lambda d: (d.name.casefold(), d.id))

    def last_seen(self, device_id: str) -> float | None:
        return self._last_seen.get(device_id)

    def upsert(self, device: Device) -> None:
        """Record that `device` was just seen, publishing DeviceAdded or DeviceUpdated."""
        if self._redactor is not None:
            self._redactor.add(device.name, "device")
            self._redactor.add(device.id, "id")
        previous = self._devices.get(device.id)
        self._devices[device.id] = device
        self._last_seen[device.id] = self._clock()
        if previous is None:
            self._bus.publish(DeviceAdded(device))
        elif previous != device:
            self._bus.publish(DeviceUpdated(device, previous))

    def expire(self, max_age: float) -> list[Device]:
        """Drop devices not seen for more than `max_age` seconds, publishing DeviceLost."""
        now = self._clock()
        stale = [i for i, seen in self._last_seen.items() if now - seen > max_age]
        lost: list[Device] = []
        for device_id in stale:
            device = self._devices.pop(device_id)
            del self._last_seen[device_id]
            lost.append(device)
            self._bus.publish(DeviceLost(device))
        return lost
