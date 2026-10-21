"""A stand-in backend with invented devices, so the UI can run without the engine or a network.

Behaviour worth seeing in the UI:
- devices appear one at a time, as discovery would find them;
- the TV needs PIN pairing first, with two PINs like a real Apple TV (remote control, then
  AirPlay); any 4 digits work except 0000, which is "wrong";
- the soundbar's first connection attempt fails, so the retry state shows.

The appearance setting is kept in memory, or in a small JSON file when `appearance_file` is
given, so a background picked in Settings survives a restart.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path

from tandem.ui.backend import (
    Appearance,
    AppearanceChanged,
    BackendEvent,
    DeviceKind,
    DeviceRemoved,
    DeviceSnapshot,
    DeviceUpdated,
    DiscoveryChanged,
    LinkState,
    Listener,
    PairingError,
    PairingFlow,
    Theme,
    Unsubscribe,
    WrongPinError,
)

_LOGGER = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]

WRONG_PIN = "0000"
TV_PIN_STEPS = 2

# Invented devices only (docs/PRIVACY.md).
DEMO_DEVICES = (
    DeviceSnapshot("demo-tv", "Living Room TV", DeviceKind.APPLE_TV, needs_pairing=True),
    DeviceSnapshot("demo-speaker-1", "Patio Speaker", DeviceKind.HOMEPOD),
    DeviceSnapshot("demo-speaker-2", "Office Speaker", DeviceKind.HOMEPOD),
    DeviceSnapshot("demo-soundbar", "Den Soundbar", DeviceKind.RECEIVER),
)
FLAKY_DEVICE = "demo-soundbar"


class DemoBackend:
    def __init__(
        self,
        *,
        sleep: Sleep = asyncio.sleep,
        delay: float = 0.6,
        retry_after: float = 2.0,
        appearance_file: Path | None = None,
    ):
        self._sleep = sleep
        self._appearance_file = appearance_file
        self._appearance = _load_appearance(appearance_file)
        self._delay = delay
        self._retry_after = retry_after
        self._devices: dict[str, DeviceSnapshot] = {}
        self._listeners: list[Listener] = []
        self._connecting: dict[str, asyncio.Task[None]] = {}
        self._flaky = {FLAKY_DEVICE}

    def subscribe(self, listener: Listener) -> Unsubscribe:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def devices(self) -> list[DeviceSnapshot]:
        return list(self._devices.values())

    async def start(self) -> None:
        self._publish(DiscoveryChanged(active=True))
        for device in DEMO_DEVICES:
            await self._sleep(self._delay / 2)
            self._set(device)
        self._publish(DiscoveryChanged(active=False))

    async def stop(self) -> None:
        for task in list(self._connecting.values()):
            task.cancel()
        self._connecting.clear()

    async def connect(self, device_id: str) -> None:
        device = self._get(device_id)
        if device.needs_pairing:
            raise PairingError("Pair this device first.")
        if device_id in self._connecting or device.state is LinkState.CONNECTED:
            return
        task = asyncio.get_running_loop().create_task(self._connect(device_id))
        self._connecting[device_id] = task
        try:
            await asyncio.wait({task})
        finally:
            if self._connecting.get(device_id) is task:
                del self._connecting[device_id]
        if not task.cancelled():
            task.result()

    async def disconnect(self, device_id: str) -> None:
        task = self._connecting.pop(device_id, None)
        if task is not None:
            task.cancel()
        self._update(device_id, state=LinkState.DISCONNECTED, retry_in=None)

    async def begin_pairing(self, device_id: str) -> PairingFlow:
        device = self._get(device_id)
        if not device.needs_pairing:
            raise PairingError("This device doesn't need pairing.")
        await self._sleep(self._delay)
        return _DemoPairing(
            TV_PIN_STEPS, lambda pin, last: self._finish_pairing(device_id, pin, last)
        )

    def appearance(self) -> Appearance:
        return self._appearance

    async def set_appearance(self, appearance: Appearance) -> None:
        self._appearance = appearance
        if self._appearance_file is not None:
            _save_appearance(self._appearance_file, appearance)
        self._publish(AppearanceChanged(appearance))

    # Internals

    async def _connect(self, device_id: str) -> None:
        self._update(device_id, state=LinkState.CONNECTING, retry_in=None)
        await self._sleep(self._delay)
        if device_id in self._flaky:
            self._flaky.discard(device_id)
            self._update(device_id, state=LinkState.WAITING, retry_in=self._retry_after)
            await self._sleep(self._retry_after)
            self._update(device_id, state=LinkState.CONNECTING, retry_in=None)
            await self._sleep(self._delay)
        self._update(device_id, state=LinkState.CONNECTED)

    async def _finish_pairing(self, device_id: str, pin: str, last: bool) -> None:
        await self._sleep(self._delay)
        if pin == WRONG_PIN:
            raise WrongPinError("That PIN didn't match.")
        if last:
            self._update(device_id, needs_pairing=False)

    def _get(self, device_id: str) -> DeviceSnapshot:
        try:
            return self._devices[device_id]
        except KeyError:
            raise PairingError("That device is no longer available.") from None

    def _update(
        self,
        device_id: str,
        *,
        state: LinkState | None = None,
        retry_in: float | None = None,
        needs_pairing: bool | None = None,
    ) -> None:
        device = self._devices.get(device_id)
        if device is None:
            return
        device = replace(
            device,
            state=device.state if state is None else state,
            retry_in=retry_in,
            needs_pairing=device.needs_pairing if needs_pairing is None else needs_pairing,
        )
        self._set(device)

    def _set(self, device: DeviceSnapshot) -> None:
        self._devices[device.id] = device
        self._publish(DeviceUpdated(device))

    def remove(self, device_id: str) -> None:
        """Forget a device, as if it left the network (used by tests)."""
        if self._devices.pop(device_id, None) is not None:
            self._publish(DeviceRemoved(device_id))

    def _publish(self, event: BackendEvent) -> None:
        for listener in list(self._listeners):
            listener(event)


def _load_appearance(path: Path | None) -> Appearance:
    if path is None or not path.exists():
        return Appearance()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Appearance(Theme(data["theme"]), str(data["background"]))
    except (OSError, ValueError, KeyError, TypeError):
        _LOGGER.warning("Ignoring an unreadable appearance file; using the defaults")
        return Appearance()


def _save_appearance(path: Path, appearance: Appearance) -> None:
    data = {"theme": appearance.theme.value, "background": appearance.background}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        _LOGGER.warning("Couldn't save the appearance setting")


class _DemoPairing:
    def __init__(self, steps: int, finish: Callable[[str, bool], Awaitable[None]]) -> None:
        self._steps = steps
        self._done = 0
        self._finish = finish

    @property
    def steps(self) -> int:
        return self._steps

    async def submit_pin(self, pin: str) -> bool:
        last = self._done + 1 == self._steps
        await self._finish(pin, last)
        self._done += 1
        return not last

    async def cancel(self) -> None:
        return None
