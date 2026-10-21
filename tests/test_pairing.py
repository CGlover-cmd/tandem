from __future__ import annotations

import asyncio

import pytest

from conftest import FakePairingHandle
from tandem.engine import pairing
from tandem.engine.events import EventBus
from tandem.engine.models import Service
from tandem.engine.pairing import PairingError, PairingState, PairingStateChanged

DEVICE_ID = "AA:BB:CC:00:00:02"


def _factory(handle: FakePairingHandle) -> pairing.PairingFactory:
    async def start() -> FakePairingHandle:
        return handle

    return start


def _pin(value: str) -> pairing.PinProvider:
    async def provide() -> str:
        return value

    return provide


async def _run(handle: FakePairingHandle, pin: str = "1234", **kwargs: object):
    bus = EventBus()
    states: list[PairingStateChanged] = []
    bus.subscribe(PairingStateChanged, states.append)
    error: PairingError | None = None
    try:
        await pairing.pair(
            DEVICE_ID,
            Service.COMPANION,
            _factory(handle),
            _pin(pin),
            bus,
            **kwargs,  # type: ignore[arg-type]
        )
    except PairingError as exc:
        error = exc
    return [s.state for s in states], states, error


async def test_pairs_with_the_pin_the_device_shows() -> None:
    saved: list[bool] = []

    async def on_paired() -> None:
        saved.append(True)

    handle = FakePairingHandle()
    states, events, error = await _run(handle, " 1234\n", on_paired=on_paired)
    assert error is None
    assert states == [PairingState.STARTED, PairingState.PIN_REQUIRED, PairingState.PAIRED]
    assert handle.entered == "1234"
    assert handle.closed
    assert saved == [True]
    assert events[0].device_id == DEVICE_ID
    assert events[0].service is Service.COMPANION


async def test_wrong_pin_fails_and_saves_nothing() -> None:
    saved: list[bool] = []

    async def on_paired() -> None:
        saved.append(True)

    handle = FakePairingHandle(accept_pin="9999")
    states, events, error = await _run(handle, "1234", on_paired=on_paired)
    assert error is not None
    assert error.reason == pairing.NOT_PAIRED
    assert states[-1] is PairingState.FAILED
    assert events[-1].reason == pairing.NOT_PAIRED
    assert saved == []
    assert handle.closed


@pytest.mark.parametrize("pin", ["12", "abcd", "12345", ""])
async def test_malformed_pin_is_rejected_before_sending(pin: str) -> None:
    handle = FakePairingHandle()
    _, _, error = await _run(handle, pin)
    assert error is not None
    assert error.reason == pairing.INVALID_PIN
    assert handle.entered is None


async def test_pin_timeout() -> None:
    async def never() -> str:
        await asyncio.Event().wait()
        return ""

    bus = EventBus()
    handle = FakePairingHandle()
    with pytest.raises(PairingError) as caught:
        await pairing.pair(
            DEVICE_ID, Service.AIRPLAY, _factory(handle), never, bus, pin_timeout=0.01
        )
    assert caught.value.reason == pairing.PIN_TIMEOUT
    assert handle.closed


async def test_device_without_pin_pairs_directly() -> None:
    handle = FakePairingHandle(provides_pin=False)
    states, _, error = await _run(handle)
    assert error is None
    assert PairingState.PIN_REQUIRED not in states
    assert handle.entered is None


async def test_protocol_error_is_reported_by_type() -> None:
    handle = FakePairingHandle(fail_begin=ConnectionRefusedError("details with 192.0.2.10"))
    _, events, error = await _run(handle)
    assert error is not None
    assert error.reason == "ConnectionRefusedError"
    assert events[-1].reason == "ConnectionRefusedError"
    assert handle.closed


async def test_factory_failure_is_reported() -> None:
    async def broken() -> FakePairingHandle:
        raise OSError("unreachable")

    bus = EventBus()
    with pytest.raises(PairingError) as caught:
        await pairing.pair(DEVICE_ID, Service.COMPANION, broken, _pin("1234"), bus)
    assert caught.value.reason == "OSError"
