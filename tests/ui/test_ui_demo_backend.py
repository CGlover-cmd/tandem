from __future__ import annotations

import re
from pathlib import Path

import pytest

from tandem.ui.backend import (
    BACKGROUNDS,
    Appearance,
    AppearanceChanged,
    BackendEvent,
    ControlError,
    ControlsChanged,
    DeviceSnapshot,
    DeviceUpdated,
    DiscoveryChanged,
    KeyAction,
    LinkState,
    MediaCommand,
    PairingError,
    RemoteKey,
    Theme,
    Volume,
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

    assert flow.steps == 2
    with pytest.raises(WrongPinError):
        await flow.submit_pin(WRONG_PIN)
    assert await flow.submit_pin("1234") is True  # second PIN follows
    assert await flow.submit_pin("5678") is False

    tv: DeviceSnapshot = next(d for d in backend.devices() if d.id == "demo-tv")
    assert not tv.needs_pairing


async def test_speakers_need_no_pairing(backend: DemoBackend) -> None:
    await backend.start()

    with pytest.raises(PairingError):
        await backend.begin_pairing("demo-speaker-1")


async def test_appearance_defaults_and_publishes_changes(backend: DemoBackend) -> None:
    events: list[BackendEvent] = []
    backend.subscribe(events.append)
    assert backend.appearance() == Appearance()

    choice = Appearance(Theme.DARK, "aurora")
    await backend.set_appearance(choice)

    assert backend.appearance() == choice
    assert events == [AppearanceChanged(choice)]


async def test_appearance_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "ui" / "appearance.json"
    await DemoBackend(appearance_file=path).set_appearance(Appearance(Theme.LIGHT, "dusk"))

    assert DemoBackend(appearance_file=path).appearance() == Appearance(Theme.LIGHT, "dusk")


def test_unreadable_appearance_file_falls_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "appearance.json"
    path.write_text('{"theme": "neon", "background": "plaid"}', encoding="utf-8")

    assert DemoBackend(appearance_file=path).appearance() == Appearance()


def test_unknown_background_is_rejected() -> None:
    with pytest.raises(ValueError, match="background"):
        Appearance(Theme.SYSTEM, "plaid")


def test_front_end_offers_the_same_backgrounds() -> None:
    theme = Path(__file__).parents[2] / "web" / "src" / "theme.ts"
    ids = re.findall(r'^\s+id: "([a-z]+)",$', theme.read_text(encoding="utf-8"), re.MULTILINE)

    assert tuple(ids) == BACKGROUNDS


async def test_demo_controls_follow_the_connection(backend: DemoBackend) -> None:
    await backend.start()
    events: list[BackendEvent] = []
    backend.subscribe(events.append)

    await backend.connect("demo-speaker-1")
    controls = backend.controls("demo-speaker-1")
    assert controls is not None
    assert controls.volume is Volume.LEVEL
    assert ControlsChanged("demo-speaker-1", controls) in events

    await backend.disconnect("demo-speaker-1")
    assert backend.controls("demo-speaker-1") is None


async def test_demo_controls_refuse_what_a_device_cannot_do(backend: DemoBackend) -> None:
    await backend.start()
    with pytest.raises(ControlError, match="isn't connected"):
        await backend.media("demo-soundbar", MediaCommand.NEXT)

    await backend.connect("demo-soundbar")
    for attempt in (
        backend.press("demo-soundbar", RemoteKey.PLAY_PAUSE, KeyAction.TAP),
        backend.media("demo-soundbar", MediaCommand.NEXT),
        backend.set_power("demo-soundbar", False),
    ):
        with pytest.raises(ControlError, match="can't do that"):
            await attempt
    await backend.press("demo-soundbar", RemoteKey.VOLUME_UP, KeyAction.TAP)
    await backend.set_volume("demo-soundbar", 250)
    controls = backend.controls("demo-soundbar")
    assert controls is not None
    assert controls.volume_level == 100.0


async def test_demo_speaker_volume_keys_need_a_volume(backend: DemoBackend) -> None:
    await backend.start()
    await backend.connect("demo-speaker-2")
    await backend.press("demo-speaker-2", RemoteKey.VOLUME_DOWN, KeyAction.TAP)
    with pytest.raises(ControlError, match="isn't connected"):
        await backend.set_volume("demo-tv", 10)
