"""Attaches a controller to each connected device and turns its pushes into events."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress

from tandem.engine.control import (
    CapabilitiesChanged,
    Capability,
    ControlError,
    Controller,
    ControlsAvailable,
    ControlStatus,
    ControlsUnavailable,
    ControlUpdate,
    DeviceControls,
    NowPlaying,
    NowPlayingChanged,
    PowerChanged,
    PowerState,
    VolumeChanged,
    VolumeControl,
)
from tandem.engine.events import EventBus
from tandem.engine.session import ConnectionState, ConnectionStateChanged, Link

_LOGGER = logging.getLogger(__name__)

ControllerFactory = Callable[[Link], Controller | None]
LinkLookup = Callable[[str], Link | None]


class _Attached:
    def __init__(self, controller: Controller) -> None:
        self.controller = controller
        self.now_playing = NowPlaying()
        self.capabilities: frozenset[Capability] = controller.capabilities()
        self.volume_control: VolumeControl = controller.volume_control()


class ControlHub:
    def __init__(self, bus: EventBus, factory: ControllerFactory, link: LinkLookup) -> None:
        self._bus = bus
        self._factory = factory
        self._link = link
        self._attached: dict[str, _Attached] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        bus.subscribe(ConnectionStateChanged, self._on_state)

    def controls(self, device_id: str) -> DeviceControls:
        return DeviceControls(
            device_id,
            lambda: self._controller(device_id),
            lambda: self._now_playing(device_id),
        )

    def _controller(self, device_id: str) -> Controller | None:
        attached = self._attached.get(device_id)
        return attached.controller if attached else None

    def _now_playing(self, device_id: str) -> NowPlaying:
        attached = self._attached.get(device_id)
        return attached.now_playing if attached else NowPlaying()

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        for device_id in list(self._attached):
            self._detach(device_id)

    def _on_state(self, event: ConnectionStateChanged) -> None:
        if event.state is ConnectionState.CONNECTED:
            self._attach(event.device_id)
        elif event.device_id in self._attached:
            self._detach(event.device_id)

    def _attach(self, device_id: str) -> None:
        link = self._link(device_id)
        controller = self._factory(link) if link is not None else None
        if controller is None:
            return
        attached = _Attached(controller)
        self._attached[device_id] = attached
        controller.start(lambda update: self._on_update(device_id, attached, update))
        task = asyncio.get_running_loop().create_task(self._announce(device_id, attached))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _announce(self, device_id: str, attached: _Attached) -> None:
        controller = attached.controller
        if Capability.NOW_PLAYING in attached.capabilities:
            try:
                attached.now_playing = await controller.now_playing()
            except (ControlError, OSError) as exc:
                _LOGGER.info("Reading now-playing failed (%s)", type(exc).__name__)
        if self._attached.get(device_id) is not attached:
            return  # disconnected while reading
        self._bus.publish(
            ControlsAvailable(
                device_id,
                ControlStatus(
                    capabilities=attached.capabilities,
                    volume_control=attached.volume_control,
                    volume=controller.volume(),
                    power=controller.power(),
                    now_playing=attached.now_playing,
                ),
            )
        )

    def _detach(self, device_id: str) -> None:
        attached = self._attached.pop(device_id)
        with suppress(Exception):
            attached.controller.stop()
        self._bus.publish(ControlsUnavailable(device_id))

    def _on_update(self, device_id: str, attached: _Attached, update: ControlUpdate) -> None:
        if self._attached.get(device_id) is not attached:
            return  # a late push from a connection that has gone
        if isinstance(update, NowPlaying):
            attached.now_playing = update
            self._bus.publish(NowPlayingChanged(device_id, update))
        elif isinstance(update, PowerState):
            self._bus.publish(PowerChanged(device_id, update))
        elif isinstance(update, float | int):
            self._bus.publish(VolumeChanged(device_id, float(update)))
        # Capabilities can change with any push (an Apple TV offers more while playing).
        try:
            capabilities = attached.controller.capabilities()
            volume_control = attached.controller.volume_control()
        except Exception as exc:  # a push racing the connection closing
            _LOGGER.debug("Reading capabilities after a push failed (%s)", type(exc).__name__)
            return
        if (capabilities, volume_control) != (attached.capabilities, attached.volume_control):
            attached.capabilities, attached.volume_control = capabilities, volume_control
            self._bus.publish(CapabilitiesChanged(device_id, capabilities, volume_control))
