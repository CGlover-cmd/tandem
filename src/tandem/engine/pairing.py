"""Pairing flow: begin, collect the PIN the device shows, finish, save the credentials.

Protocol-agnostic: a `PairingHandle` does the protocol work (the pyatv one is in `adapters`).
Progress is published as `PairingStateChanged` events so the UI can show a PIN sheet.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from tandem.engine.events import Event, EventBus
from tandem.engine.models import Service

_LOGGER = logging.getLogger(__name__)

_PIN = re.compile(r"\d{4}")
DEFAULT_PIN_TIMEOUT = 180.0


class PairingState(Enum):
    STARTED = "started"
    PIN_REQUIRED = "pin_required"  # the device is showing a PIN for the user to type in
    PAIRED = "paired"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PairingStateChanged(Event):
    device_id: str
    service: Service
    state: PairingState
    reason: str | None = None
    """Why it failed: an exception type name or one of the reasons below."""


class PairingError(Exception):
    """Pairing didn't complete. `reason` is safe to show and log (no addresses or PINs)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


INVALID_PIN = "InvalidPin"  # not four digits
PIN_TIMEOUT = "PinTimeout"  # nobody typed the PIN in time
NOT_PAIRED = "NotPaired"  # the device rejected the PIN


class PairingHandle(Protocol):
    @property
    def device_provides_pin(self) -> bool: ...

    @property
    def has_paired(self) -> bool: ...

    async def begin(self) -> None: ...
    def pin(self, pin: str) -> None: ...
    async def finish(self) -> None: ...
    async def close(self) -> None: ...


PairingFactory = Callable[[], Awaitable[PairingHandle]]
PinProvider = Callable[[], Awaitable[str]]
"""Return the PIN the user read off the device."""


async def pair(
    device_id: str,
    service: Service,
    factory: PairingFactory,
    pin_provider: PinProvider,
    bus: EventBus,
    *,
    on_paired: Callable[[], Awaitable[None]] | None = None,
    pin_timeout: float = DEFAULT_PIN_TIMEOUT,
) -> None:
    """Pair `service` on a device. Raises PairingError (after publishing FAILED) on failure."""

    def publish(state: PairingState, reason: str | None = None) -> None:
        bus.publish(PairingStateChanged(device_id, service, state, reason))

    publish(PairingState.STARTED)
    try:
        handle = await factory()
    except Exception as exc:
        publish(PairingState.FAILED, type(exc).__name__)
        raise PairingError(type(exc).__name__) from exc

    try:
        await handle.begin()
        if handle.device_provides_pin:
            publish(PairingState.PIN_REQUIRED)
            try:
                pin = (await asyncio.wait_for(pin_provider(), pin_timeout)).strip()
            except TimeoutError:
                raise PairingError(PIN_TIMEOUT) from None
            if not _PIN.fullmatch(pin):
                raise PairingError(INVALID_PIN)
            handle.pin(pin)
        await handle.finish()
        if not handle.has_paired:
            raise PairingError(NOT_PAIRED)
        if on_paired is not None:
            await on_paired()
    except PairingError as exc:
        publish(PairingState.FAILED, exc.reason)
        raise
    except Exception as exc:
        reason = type(exc).__name__
        # The message helps diagnose protocol errors; the log redacts any address in it.
        _LOGGER.info(
            "Pairing %s with %s failed (%s: %s)",
            service.value,
            device_id,
            reason,
            exc,
            exc_info=_LOGGER.isEnabledFor(logging.DEBUG),
        )
        publish(PairingState.FAILED, reason)
        raise PairingError(reason) from exc
    finally:
        with suppress(Exception):
            await handle.close()
    publish(PairingState.PAIRED)
