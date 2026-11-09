"""The demo: the real bridge and engine on invented devices (ADR-0019)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from demo_harness import demo_backend, settle

from tandem.bridge import DemoBackend
from tandem.engine.adapters.demo import DEMO_DEVICES, FLAKY, WRONG_PIN
from tandem.ui.backend import (
    BACKGROUNDS,
    PHOTO_BACKGROUND,
    Appearance,
    AppearanceChanged,
    BackendEvent,
    ControlError,
    DeviceUpdated,
    KeyAction,
    LinkState,
    MediaCommand,
    PairingError,
    RemoteKey,
    Theme,
    WrongPinError,
)


async def _started(backend: DemoBackend) -> list[BackendEvent]:
    events: list[BackendEvent] = []
    backend.subscribe(events.append)
    await backend.start()
    return events


def _state(backend: DemoBackend, device_id: str) -> LinkState:
    return next(d for d in backend.devices() if d.id == device_id).state


async def test_start_finds_every_demo_device(backend: DemoBackend) -> None:
    await _started(backend)
    assert {d.id for d in backend.devices()} == {d.id for d in DEMO_DEVICES}
    tv = next(d for d in backend.devices() if d.id == "demo-tv")
    assert tv.needs_pairing


async def test_the_flaky_soundbar_waits_then_retries(backend: DemoBackend) -> None:
    events = await _started(backend)
    await backend.connect(FLAKY)
    await settle()
    states = [
        e.device.state for e in events if isinstance(e, DeviceUpdated) and e.device.id == FLAKY
    ]
    assert LinkState.WAITING in states
    assert _state(backend, FLAKY) is LinkState.CONNECTED
    await backend.disconnect(FLAKY)
    assert _state(backend, FLAKY) is LinkState.DISCONNECTED


async def test_the_tv_pairs_with_two_pins_and_rejects_0000(backend: DemoBackend) -> None:
    await _started(backend)
    with pytest.raises(PairingError):
        await backend.connect("demo-tv")
    flow = await backend.begin_pairing("demo-tv")
    assert flow.steps == 2
    with pytest.raises(WrongPinError):
        await flow.submit_pin(WRONG_PIN)
    assert await flow.submit_pin("1234") is True  # now the AirPlay PIN
    assert await flow.submit_pin("1234") is False
    assert not next(d for d in backend.devices() if d.id == "demo-tv").needs_pairing
    with pytest.raises(PairingError, match="noPairingNeeded"):
        await backend.begin_pairing("demo-speaker-1")


async def test_controls_follow_the_connection_and_refuse_what_a_device_cannot_do(
    backend: DemoBackend,
) -> None:
    await _started(backend)
    with pytest.raises(ControlError, match="notConnected"):
        await backend.press("demo-speaker-1", RemoteKey.UP, KeyAction.TAP)
    await backend.connect("demo-speaker-1")
    await settle()
    controls = backend.controls("demo-speaker-1")
    assert controls is not None
    assert controls.volume_level == 40.0
    with pytest.raises(ControlError, match="cantDoThat"):
        await backend.press("demo-speaker-1", RemoteKey.UP, KeyAction.TAP)  # no remote
    with pytest.raises(ControlError, match="cantDoThat"):
        await backend.set_power("demo-speaker-1", False)
    await backend.media("demo-speaker-1", MediaCommand.PLAY_PAUSE)
    await settle()
    playing = backend.controls("demo-speaker-1")
    assert playing is not None
    assert playing.now_playing is not None
    assert playing.now_playing.state == "playing"
    await backend.disconnect("demo-speaker-1")
    await settle()
    assert backend.controls("demo-speaker-1") is None


async def test_search_brings_up_the_keyboard_and_back_closes_it(backend: DemoBackend) -> None:
    await _started(backend)
    flow = await backend.begin_pairing("demo-tv")
    await flow.submit_pin("1234")
    await flow.submit_pin("1234")
    await backend.connect("demo-tv")
    await settle()
    await backend.launch_app("demo-tv", "com.apple.TVSearch")
    await settle()
    assert backend.controls("demo-tv").keyboard  # type: ignore[union-attr]
    await backend.press("demo-tv", RemoteKey.MENU, KeyAction.TAP)
    await settle()
    assert not backend.controls("demo-tv").keyboard  # type: ignore[union-attr]


async def test_appearance_defaults_and_publishes_changes(backend: DemoBackend) -> None:
    events: list[BackendEvent] = []
    backend.subscribe(events.append)
    assert backend.appearance() == Appearance()
    choice = Appearance(Theme.DARK, "aurora")
    await backend.set_appearance(choice)
    assert backend.appearance() == choice
    assert AppearanceChanged(choice) in events


async def test_appearance_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "ui" / "demo-settings.json"
    await demo_backend(settings_file=path).set_appearance(Appearance(Theme.LIGHT, "dusk"))
    assert demo_backend(settings_file=path).appearance() == Appearance(Theme.LIGHT, "dusk")


def test_unreadable_settings_fall_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "demo-settings.json"
    path.write_text('{"theme": "neon", "background": "plaid"}', encoding="utf-8")
    assert demo_backend(settings_file=path).appearance() == Appearance()


def test_unknown_background_is_rejected() -> None:
    with pytest.raises(ValueError, match="background"):
        Appearance(Theme.SYSTEM, "plaid")


def test_front_end_offers_the_same_backgrounds() -> None:
    theme = Path(__file__).parents[2] / "web" / "src" / "theme.ts"
    ids = re.findall(r'^\s+id: "([a-z]+)",$', theme.read_text(encoding="utf-8"), re.MULTILINE)
    assert (*ids, PHOTO_BACKGROUND) == BACKGROUNDS


async def test_typed_commands_run_on_the_demo(backend: DemoBackend) -> None:
    await _started(backend)
    await backend.connect("demo-speaker-1")
    await settle()
    result = await backend.run_command("volume 30 on patio speaker")
    assert (result.status, result.code) == ("done", "volumeSet")
    await settle()
    assert backend.controls("demo-speaker-1").volume_level == 30.0  # type: ignore[union-attr]
    sent = await backend.run_command("send audio to office speaker")
    assert sent.status == "done"
