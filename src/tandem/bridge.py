"""The real engine behind the window: the UI's `Backend` contract (ADR-0008) on `Engine`.

This is the one module that imports both `tandem.engine` and `tandem.ui`; the two layers
never import each other. `DemoBackend` implements the same contract with invented devices.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass

from tandem.engine import pairing as engine_pairing
from tandem.engine.events import EventBus
from tandem.engine.models import Device, Service
from tandem.engine.registry import DeviceEvent, DeviceLost
from tandem.engine.service import Engine, UnknownDeviceError
from tandem.engine.session import ConnectionState, ConnectionStateChanged
from tandem.engine.settings import SettingsChanged, SettingsStore
from tandem.engine.settings import Theme as EngineTheme
from tandem.ui import backend as ui

_LOGGER = logging.getLogger(__name__)

# Gives up after this many failed attempts in a row; the card then offers "Try again".
MAX_ATTEMPTS = 6

# How pyatv reports a PIN the device rejected (an exception type name, or the engine's own).
_WRONG_PIN = {engine_pairing.NOT_PAIRED, "PairingError", "AuthenticationError"}

# Words the window shows. Safe to show: no names, addresses or PINs.
NOT_AVAILABLE = "That device is no longer available."
PAIR_FIRST = "Pair this device first."
NO_PAIRING_NEEDED = "This device doesn't need pairing."
PIN_EXPIRED = "The PIN expired. Try again."
COULD_NOT_PAIR = "Tandem couldn't pair with this device. Make sure it's on and try again."
WRONG_PIN = "That PIN didn't match."

_LINK = {
    ConnectionState.DISCONNECTED: ui.LinkState.DISCONNECTED,
    ConnectionState.CONNECTING: ui.LinkState.CONNECTING,
    ConnectionState.CONNECTED: ui.LinkState.CONNECTED,
    ConnectionState.WAITING: ui.LinkState.WAITING,
    ConnectionState.FAILED: ui.LinkState.FAILED,
}


@dataclass(frozen=True, slots=True)
class _Link:
    state: ui.LinkState = ui.LinkState.DISCONNECTED
    retry_in: float | None = None


class EngineBackend:
    def __init__(
        self,
        engine: Engine,
        settings: SettingsStore,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        pin_timeout: float = engine_pairing.DEFAULT_PIN_TIMEOUT,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._max_attempts = max_attempts
        self._pin_timeout = pin_timeout
        self._listeners: list[ui.Listener] = []
        self._links: dict[str, _Link] = {}
        bus = engine.bus
        self._unsubscribe = [
            bus.subscribe(DeviceEvent, self._on_device),
            bus.subscribe(ConnectionStateChanged, self._on_connection),
            bus.subscribe(SettingsChanged, self._on_settings),
        ]

    # Observing

    def subscribe(self, listener: ui.Listener) -> ui.Unsubscribe:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def devices(self) -> list[ui.DeviceSnapshot]:
        return [self._snapshot(d) for d in self._engine.registry.devices()]

    def appearance(self) -> ui.Appearance:
        settings = self._settings.settings
        background = settings.background
        if background not in ui.BACKGROUNDS:
            background = ui.Appearance().background
        return ui.Appearance(ui.Theme(settings.theme.value), background)

    # Lifecycle

    async def start(self) -> None:
        await self._engine.open()
        self._publish(ui.DiscoveryChanged(active=True))
        try:
            await self._engine.scan()
        except Exception as exc:
            _LOGGER.warning("First discovery scan failed (%s)", type(exc).__name__)
        finally:
            self._publish(ui.DiscoveryChanged(active=False))
        self._engine.discovery.start()

    async def stop(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe = []
        await self._engine.close()

    # Commands

    async def connect(self, device_id: str) -> None:
        device = self._device(device_id)
        if engine_pairing.services_to_pair(device):
            raise ui.PairingError(PAIR_FIRST)
        # Start and return: progress arrives as ConnectionStateChanged events.
        self._engine.session(device_id, max_attempts=self._max_attempts).start()

    async def disconnect(self, device_id: str) -> None:
        await self._engine.disconnect(device_id)
        self._set_link(device_id, _Link())

    async def begin_pairing(self, device_id: str) -> ui.PairingFlow:
        device = self._device(device_id)
        services = engine_pairing.services_to_pair(device)
        if not services:
            raise ui.PairingError(NO_PAIRING_NEEDED)
        flow = _EnginePairing(self._engine, device_id, services, self._pin_timeout)
        await flow.start()
        return flow

    async def set_appearance(self, appearance: ui.Appearance) -> None:
        # The store publishes SettingsChanged on the engine's bus, which `_on_settings` relays.
        self._settings.update(
            theme=EngineTheme(appearance.theme.value), background=appearance.background
        )

    # Engine events

    def _on_device(self, event: DeviceEvent) -> None:
        if isinstance(event, DeviceLost):
            self._links.pop(event.device.id, None)
            self._publish(ui.DeviceRemoved(event.device.id))
        else:
            self._publish(ui.DeviceUpdated(self._snapshot(event.device)))

    def _on_connection(self, event: ConnectionStateChanged) -> None:
        self._set_link(event.device_id, _Link(_LINK[event.state], event.retry_in))

    def _on_settings(self, event: SettingsChanged) -> None:
        self._publish(ui.AppearanceChanged(self.appearance()))

    # Internals

    def _device(self, device_id: str) -> Device:
        try:
            return self._engine.device(device_id)
        except UnknownDeviceError:
            raise ui.PairingError(NOT_AVAILABLE) from None

    def _set_link(self, device_id: str, link: _Link) -> None:
        self._links[device_id] = link
        device = self._engine.registry.get(device_id)
        if device is not None:
            self._publish(ui.DeviceUpdated(self._snapshot(device)))

    def _snapshot(self, device: Device) -> ui.DeviceSnapshot:
        link = self._links.get(device.id, _Link())
        return ui.DeviceSnapshot(
            id=device.id,
            name=device.name,
            kind=ui.DeviceKind(device.kind.value),
            state=link.state,
            needs_pairing=bool(engine_pairing.services_to_pair(device)),
            retry_in=link.retry_in if link.state is ui.LinkState.WAITING else None,
        )

    def _publish(self, event: ui.BackendEvent) -> None:
        for listener in list(self._listeners):
            listener(event)


class _EnginePairing:
    """Pairs each service in turn; each one makes the device show a new PIN.

    The engine's `pair` asks for the PIN through a callback. Here that callback signals that
    the device is now showing a PIN, then waits for the user to type it into the window.
    """

    def __init__(
        self, engine: Engine, device_id: str, services: list[Service], pin_timeout: float
    ) -> None:
        self._engine = engine
        self._device_id = device_id
        self._services = list(services)
        self._pin_timeout = pin_timeout
        self._index = 0
        self._task: asyncio.Task[None] | None = None
        self._pin: asyncio.Future[str] | None = None

    @property
    def steps(self) -> int:
        return len(self._services)

    async def start(self) -> None:
        await self._show_next_pin()

    async def submit_pin(self, pin: str) -> bool:
        task, future = self._task, self._pin
        if task is None or future is None:
            return False  # everything paired without a PIN
        if not future.done():
            future.set_result(pin)
        try:
            await task
        except engine_pairing.PairingError as error:
            if error.reason in _WRONG_PIN:
                await self._show_next_pin()  # the same service again: the device shows a new PIN
                raise ui.WrongPinError(WRONG_PIN) from None
            raise ui.PairingError(_message(error.reason)) from None
        self._index += 1
        return await self._show_next_pin()

    async def cancel(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError, engine_pairing.PairingError):
                await task

    async def _show_next_pin(self) -> bool:
        """Start pairing the current service. True once the device shows a PIN; False when
        nothing is left. Services that pair without a PIN are finished on the way."""
        loop = asyncio.get_running_loop()
        while self._index < len(self._services):
            service = self._services[self._index]
            showing: asyncio.Future[None] = loop.create_future()
            pin: asyncio.Future[str] = loop.create_future()

            async def provide(
                showing: asyncio.Future[None] = showing, pin: asyncio.Future[str] = pin
            ) -> str:
                if not showing.done():
                    showing.set_result(None)
                return await pin

            task = loop.create_task(
                self._engine.pair(
                    self._device_id,
                    service,
                    provide,
                    pin_timeout=self._pin_timeout,
                )
            )
            self._task, self._pin = task, pin
            await asyncio.wait({showing, task}, return_when=asyncio.FIRST_COMPLETED)
            if showing.done():
                return True
            try:
                task.result()
            except engine_pairing.PairingError as error:
                raise ui.PairingError(_message(error.reason)) from None
            self._index += 1  # paired without a PIN
        self._task, self._pin = None, None
        return False


def _message(reason: str) -> str:
    return PIN_EXPIRED if reason == engine_pairing.PIN_TIMEOUT else COULD_NOT_PAIR


def create_engine_backend() -> EngineBackend:  # pragma: no cover - needs the network
    """The engine as the app runs it: pyatv, the DPAPI credential vault, redacted file logs."""
    from tandem.engine import paths
    from tandem.engine.adapters.credential_vault import CredentialVault
    from tandem.engine.adapters.pyatv_adapter import PyatvBackend
    from tandem.engine.logs import configure_logging
    from tandem.engine.redact import Redactor

    redactor = Redactor()
    configure_logging(redactor, log_dir=paths.log_dir())
    bus = EventBus()
    store = SettingsStore(paths.settings_file(), bus)
    settings = store.load()
    engine = Engine(
        PyatvBackend(CredentialVault(paths.credentials_file())),
        bus=bus,
        redactor=redactor,
        discovery_interval=settings.discovery_interval_s,
    )
    return EngineBackend(engine, store)
