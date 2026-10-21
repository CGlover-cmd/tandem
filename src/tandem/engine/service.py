"""The engine's service API: what the UI and the developer tool call.

`Engine` ties discovery, the registry, pairing and connection sessions together on top of a
`Backend`, which does the protocol work (pyatv, in `adapters`). Everything here is
protocol-agnostic and tested with a fake backend.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any, Protocol

from tandem.engine import diagnostics, pairing
from tandem.engine.discovery import Discovery, Sleep
from tandem.engine.events import EventBus
from tandem.engine.models import Device, Service
from tandem.engine.pairing import PairingError, PairingFactory, PinProvider
from tandem.engine.redact import Redactor
from tandem.engine.registry import DeviceRegistry
from tandem.engine.session import ConnectionSession, Connector, Link


class Backend(Protocol):
    async def load(self) -> None:
        """Load stored credentials."""

    async def save(self) -> None:
        """Persist credentials changed by pairing or forgetting."""

    async def scan(self, timeout: float) -> Sequence[Device]: ...

    async def describe(self, device_id: str) -> Device | None:
        """The device as last scanned, with current pairing state; None if not scanned."""
        ...

    def pairing(self, device_id: str, service: Service) -> PairingFactory: ...
    def connector(self, device_id: str) -> Connector: ...

    async def forget(self, device_id: str) -> bool:
        """Delete the device's stored credentials. Returns False if there were none."""
        ...


class UnknownDeviceError(LookupError):
    """No device with that id has been discovered."""


SERVICE_NOT_OFFERED = "ServiceNotOffered"


class Engine:
    def __init__(
        self,
        backend: Backend,
        *,
        bus: EventBus | None = None,
        redactor: Redactor | None = None,
        discovery_interval: float = 10.0,
        scan_timeout: float = 3.0,
        sleep: Sleep = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.bus = bus or EventBus()
        self.redactor = redactor or Redactor()
        self.registry = DeviceRegistry(self.bus, self.redactor, clock)
        self._backend = backend
        self._sleep = sleep
        self.discovery = Discovery(
            self.registry,
            backend.scan,
            interval=discovery_interval,
            scan_timeout=scan_timeout,
            sleep=sleep,
        )
        self._sessions: dict[str, ConnectionSession] = {}

    async def open(self) -> None:
        await self._backend.load()

    async def close(self) -> None:
        """Stop discovery and disconnect everything."""
        await self.discovery.stop()
        for device_id in list(self._sessions):
            await self.disconnect(device_id)

    async def scan(self) -> list[Device]:
        """Scan once and return every visible device."""
        await self.discovery.scan_once()
        return self.registry.devices()

    def device(self, device_id: str) -> Device:
        device = self.registry.get(device_id)
        if device is None:
            raise UnknownDeviceError(device_id)
        return device

    async def pair(
        self,
        device_id: str,
        service: Service,
        pin_provider: PinProvider,
        *,
        pin_timeout: float = pairing.DEFAULT_PIN_TIMEOUT,
    ) -> None:
        """Pair one service of a discovered device and save the credentials."""
        device = self.device(device_id)
        if service not in device.services:
            raise PairingError(SERVICE_NOT_OFFERED)

        async def pin_for_logs() -> str:
            pin = await pin_provider()
            self.redactor.add(pin.strip(), "pin")  # protocol libraries may log it
            return pin

        await pairing.pair(
            device_id,
            service,
            self._backend.pairing(device_id, service),
            pin_for_logs,
            self.bus,
            on_paired=self._backend.save,
            pin_timeout=pin_timeout,
        )
        # Ask the backend for the new state rather than guessing: a protocol library may store
        # credentials for more than the one service.
        refreshed = await self._backend.describe(device_id)
        if refreshed is None:
            current = self.registry.get(device_id) or device
            refreshed = dataclasses.replace(
                current,
                paired=current.paired | {service},
                needs_pairing=current.needs_pairing - {service},
            )
        self.registry.upsert(refreshed)

    async def forget(self, device_id: str) -> bool:
        """Disconnect and delete stored credentials for a device."""
        await self.disconnect(device_id)
        removed = await self._backend.forget(device_id)
        if removed:
            await self._backend.save()
            device = self.registry.get(device_id)
            if device is not None:
                self.registry.upsert(
                    dataclasses.replace(
                        device,
                        paired=frozenset[Service](),
                        needs_pairing=device.needs_pairing | device.paired,
                    )
                )
        return removed

    def session(self, device_id: str, *, max_attempts: int | None = None) -> ConnectionSession:
        """The device's connection session, created on first use."""
        session = self._sessions.get(device_id)
        if session is None:
            session = ConnectionSession(
                device_id,
                self._backend.connector(device_id),
                self.bus,
                max_attempts=max_attempts,
                sleep=self._sleep,
            )
            self._sessions[device_id] = session
        return session

    async def connect(
        self,
        device_id: str,
        *,
        timeout: float | None = None,
        max_attempts: int | None = None,
    ) -> Link:
        """Connect (and keep reconnecting until `disconnect`). Returns the open link."""
        session = self.session(device_id, max_attempts=max_attempts)
        session.start()
        return await session.wait_connected(timeout)

    async def disconnect(self, device_id: str) -> None:
        session = self._sessions.pop(device_id, None)
        if session is not None:
            with suppress(Exception):
                await session.close()

    def diagnostics(
        self,
        out_dir: Path,
        *,
        log_dir: Path | None = None,
        settings: dict[str, Any] | None = None,
    ) -> Path:
        """Write a redacted diagnostics bundle (devices, connection states, logs)."""
        devices = [
            diagnostics.DeviceSummary(
                device,
                self._sessions[device.id].state if device.id in self._sessions else None,
            )
            for device in self.registry.devices()
        ]
        return diagnostics.write_bundle(
            out_dir, self.redactor, devices=devices, settings=settings, log_dir=log_dir
        )
