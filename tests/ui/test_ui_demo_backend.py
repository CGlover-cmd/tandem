from __future__ import annotations

import pytest

from tandem.ui.backend import (
    BackendEvent,
    DeviceSnapshot,
    DeviceUpdated,
    DiscoveryChanged,
    LinkState,
    PairingError,
    WrongPinError,
)
from tandem.ui.demo_backend import DEMO_DEVICES, FLAKY_DEVICE, WRONG_PIN, DemoBackend


def _states(events: list[BackendEvent], device_id: str) -> list[LinkState]:
    return [
        e.device.state for e in events if isinstance(e, DeviceUpdated) and e.device.id == device_id
    ]


async def test_start_announces_every_demo_device(backend: DemoBackend) -> None:
    events: list[BackendEvent] = []
    backend.subscribe(events.append)

    await backend.start()

    assert events[0] == DiscoveryChanged(active=True)
    assert events[-1] == DiscoveryChanged(active=False)
    assert {d.id for d in backend.devices()} == {d.id for d in DEMO_DEVICES}


async def test_connect_goes_through_connecting(backend: DemoBackend) -> None:
    await backend.start()
    events: list[BackendEvent] = []
    backend.subscribe(events.append)

    await backend.connect("demo-speaker-1")

    assert _states(events, "demo-speaker-1") == [LinkState.CONNECTING, LinkState.CONNECTED]


async def test_flaky_device_waits_then_retries(backend: DemoBackend) -> None:
    await backend.start()
    events: list[BackendEvent] = []
    backend.subscribe(events.append)

    await backend.connect(FLAKY_DEVICE)

    assert _states(events, FLAKY_DEVICE) == [
        LinkState.CONNECTING,
        LinkState.WAITING,
        LinkState.CONNECTING,
        LinkState.CONNECTED,
    ]


async def test_disconnect_returns_to_disconnected(backend: DemoBackend) -> None:
    await backend.start()
    await backend.connect("demo-speaker-2")

    await backend.disconnect("demo-speaker-2")

    device = next(d for d in backend.devices() if d.id == "demo-speaker-2")
    assert device.state is LinkState.DISCONNECTED


async def test_tv_must_be_paired_before_connecting(backend: DemoBackend) -> None:
    await backend.start()

    with pytest.raises(PairingError):
        await backend.connect("demo-tv")


async def test_wrong_pin_then_right_pin_pairs(backend: DemoBackend) -> None:
    await backend.start()
    flow = await backend.begin_pairing("demo-tv")

    with pytest.raises(WrongPinError):
        await flow.submit_pin(WRONG_PIN)
    await flow.submit_pin("1234")

    tv: DeviceSnapshot = next(d for d in backend.devices() if d.id == "demo-tv")
    assert not tv.needs_pairing


async def test_speakers_need_no_pairing(backend: DemoBackend) -> None:
    await backend.start()

    with pytest.raises(PairingError):
        await backend.begin_pairing("demo-speaker-1")
