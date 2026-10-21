"""The UI contract on the real engine (tandem.bridge), with the engine's fake protocol backend."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from conftest import ALL_CAPABILITIES, FakeBackend, ManualSleep, make_device
from tandem import bridge
from tandem.engine.control import (
    Capability,
    ControlError,
    ControlsUnavailable,
    KeyAction,
    MediaCommand,
    NowPlaying,
    PlayState,
    PowerChanged,
    PowerState,
    RemoteKey,
    VolumeControl,
)
from tandem.engine.events import EventBus
from tandem.engine.models import Device, DeviceKind, Service
from tandem.engine.registry import DeviceLost
from tandem.engine.service import Engine
from tandem.engine.settings import SettingsStore
from tandem.ui import backend as ui

APPLE_TV = make_device(
    id="AA:BB:CC:00:00:02",
    name="Living Room TV",
    kind=DeviceKind.APPLE_TV,
    model="Apple TV 4K",
    services=frozenset({Service.AIRPLAY, Service.RAOP, Service.COMPANION}),
    needs_pairing=frozenset({Service.AIRPLAY, Service.RAOP, Service.COMPANION}),
)
SPEAKER = make_device()  # a HomePod with no pairing needed


class Harness:
    def __init__(self, tmp_path: Path, sleep: ManualSleep) -> None:
        self.fake = FakeBackend([APPLE_TV, SPEAKER])
        bus = EventBus()
        self.settings = SettingsStore(tmp_path / "settings.json", bus)
        self.engine = Engine(self.fake, bus=bus, sleep=sleep, discovery_interval=60.0)
        self.backend = bridge.EngineBackend(self.engine, self.settings, max_attempts=2)
        self.events: list[ui.BackendEvent] = []
        self.backend.subscribe(self.events.append)

    def device(self, device_id: str) -> ui.DeviceSnapshot:
        return next(d for d in self.backend.devices() if d.id == device_id)

    def states(self, device_id: str) -> list[ui.LinkState]:
        return [
            e.device.state
            for e in self.events
            if isinstance(e, ui.DeviceUpdated) and e.device.id == device_id
        ]


@pytest.fixture
async def harness(tmp_path: Path, manual_sleep: ManualSleep) -> AsyncIterator[Harness]:
    h = Harness(tmp_path, manual_sleep)
    await h.backend.start()
    yield h
    manual_sleep.release()
    await h.backend.stop()


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


# Discovery and devices


async def test_start_scans_once_and_lists_devices(harness: Harness) -> None:
    assert harness.fake.loaded
    discovery = [e for e in harness.events if isinstance(e, ui.DiscoveryChanged)]
    assert discovery == [ui.DiscoveryChanged(active=True), ui.DiscoveryChanged(active=False)]

    tv = harness.device(APPLE_TV.id)
    assert tv.name == "Living Room TV"
    assert tv.kind is ui.DeviceKind.APPLE_TV
    assert tv.needs_pairing
    assert tv.state is ui.LinkState.DISCONNECTED
    assert not harness.device(SPEAKER.id).needs_pairing
    assert harness.engine.discovery.running


async def test_a_failing_first_scan_still_finishes_discovery(
    tmp_path: Path, manual_sleep: ManualSleep, caplog: pytest.LogCaptureFixture
) -> None:
    h = Harness(tmp_path, manual_sleep)

    async def broken(_timeout: float) -> list[Device]:
        raise OSError("no network at 192.0.2.1")

    h.engine.discovery._scanner = broken  # pyright: ignore[reportPrivateUsage]
    await h.backend.start()
    try:
        assert h.events[-1] == ui.DiscoveryChanged(active=False)
        assert "OSError" in caplog.text
        assert "192.0.2.1" not in caplog.text
    finally:
        manual_sleep.release()
        await h.backend.stop()


async def test_a_lost_device_is_removed(harness: Harness) -> None:
    harness.engine.bus.publish(DeviceLost(SPEAKER))
    assert harness.events[-1] == ui.DeviceRemoved(SPEAKER.id)


async def test_unsubscribe_stops_events(harness: Harness) -> None:
    seen: list[ui.BackendEvent] = []
    unsubscribe = harness.backend.subscribe(seen.append)
    unsubscribe()
    unsubscribe()
    harness.engine.bus.publish(DeviceLost(SPEAKER))
    assert seen == []


# Connecting


async def test_connect_and_disconnect_show_link_states(harness: Harness) -> None:
    await harness.backend.connect(SPEAKER.id)
    await _settle()
    assert harness.device(SPEAKER.id).state is ui.LinkState.CONNECTED

    await harness.backend.disconnect(SPEAKER.id)
    assert harness.device(SPEAKER.id).state is ui.LinkState.DISCONNECTED
    assert ui.LinkState.CONNECTING in harness.states(SPEAKER.id)


async def test_failed_attempts_wait_then_give_up(
    harness: Harness, manual_sleep: ManualSleep
) -> None:
    harness.fake.connect_failures[SPEAKER.id] = [OSError(), OSError()]
    sleeps = len(manual_sleep.delays)

    await harness.backend.connect(SPEAKER.id)
    await manual_sleep.until(sleeps + 1)
    waiting = harness.device(SPEAKER.id)
    assert waiting.state is ui.LinkState.WAITING
    assert waiting.retry_in is not None
    assert waiting.retry_in > 0

    manual_sleep.release()
    await _settle()
    failed = harness.device(SPEAKER.id)
    assert failed.state is ui.LinkState.FAILED
    assert failed.retry_in is None


async def test_connect_needs_pairing_first(harness: Harness) -> None:
    with pytest.raises(ui.PairingError, match="Pair this device first"):
        await harness.backend.connect(APPLE_TV.id)


async def test_unknown_devices_are_reported_plainly(harness: Harness) -> None:
    with pytest.raises(ui.PairingError, match="no longer available"):
        await harness.backend.connect("missing")
    with pytest.raises(ui.PairingError, match="no longer available"):
        await harness.backend.begin_pairing("missing")


# Pairing


async def test_apple_tv_pairs_remote_then_airplay(harness: Harness) -> None:
    flow = await harness.backend.begin_pairing(APPLE_TV.id)
    assert flow.steps == 2  # Companion and AirPlay; RAOP is covered by AirPlay

    assert await flow.submit_pin("1234") is True
    assert await flow.submit_pin("1234") is False

    assert harness.fake.credentials == {
        (APPLE_TV.id, Service.COMPANION),
        (APPLE_TV.id, Service.AIRPLAY),
    }
    assert not harness.device(APPLE_TV.id).needs_pairing
    await harness.backend.connect(APPLE_TV.id)  # now allowed


async def test_wrong_pin_shows_a_fresh_pin_for_the_same_step(harness: Harness) -> None:
    flow = await harness.backend.begin_pairing(APPLE_TV.id)

    with pytest.raises(ui.WrongPinError):
        await flow.submit_pin("9999")

    assert len(harness.fake.handles) == 2  # a new attempt, so the TV shows a new PIN
    assert harness.fake.handles[0].closed
    assert await flow.submit_pin("1234") is True


async def test_speakers_need_no_pairing(harness: Harness) -> None:
    with pytest.raises(ui.PairingError, match="doesn't need pairing"):
        await harness.backend.begin_pairing(SPEAKER.id)


async def test_pairing_that_cannot_begin_fails_plainly(harness: Harness) -> None:
    harness.fake.handle_options = {"fail_begin": OSError("refused by 192.0.2.10")}

    with pytest.raises(ui.PairingError) as failed:
        await harness.backend.begin_pairing(APPLE_TV.id)

    assert str(failed.value) == bridge.COULD_NOT_PAIR
    assert "192.0.2.10" not in str(failed.value)


async def test_a_pin_typed_too_late_says_it_expired(
    tmp_path: Path, manual_sleep: ManualSleep
) -> None:
    h = Harness(tmp_path, manual_sleep)
    h.backend = bridge.EngineBackend(h.engine, h.settings, pin_timeout=0.01)
    await h.backend.start()
    try:
        flow = await h.backend.begin_pairing(APPLE_TV.id)
        await asyncio.sleep(0.05)

        with pytest.raises(ui.PairingError, match="expired"):
            await flow.submit_pin("1234")
    finally:
        manual_sleep.release()
        await h.backend.stop()


async def test_cancel_stops_the_attempt(harness: Harness) -> None:
    flow = await harness.backend.begin_pairing(APPLE_TV.id)

    await flow.cancel()
    await flow.cancel()  # twice is harmless

    assert harness.fake.handles[0].closed
    assert harness.fake.credentials == set()


async def test_devices_that_show_no_pin_pair_straight_away(harness: Harness) -> None:
    harness.fake.handle_options = {"provides_pin": False}

    flow = await harness.backend.begin_pairing(APPLE_TV.id)

    assert await flow.submit_pin("") is False
    assert not harness.device(APPLE_TV.id).needs_pairing


# Appearance


async def test_appearance_is_saved_in_engine_settings(harness: Harness, tmp_path: Path) -> None:
    assert harness.backend.appearance() == ui.Appearance()

    await harness.backend.set_appearance(ui.Appearance(ui.Theme.DARK, "aurora"))

    assert harness.events[-1] == ui.AppearanceChanged(ui.Appearance(ui.Theme.DARK, "aurora"))
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["theme"] == "dark"
    assert saved["background"] == "aurora"


async def test_unknown_saved_background_falls_back(harness: Harness) -> None:
    harness.settings.update(background="plaid")
    assert harness.backend.appearance().background == "mist"


# Remote, media, volume and power


async def _connected(harness: Harness, **options: object) -> ui.ControlsSnapshot:
    harness.fake.controller_options = dict(options)
    await harness.backend.connect(SPEAKER.id)
    await _settle()
    controls = harness.backend.controls(SPEAKER.id)
    assert controls is not None
    return controls


async def test_controls_arrive_when_connected_and_go_when_disconnected(harness: Harness) -> None:
    assert harness.backend.controls(SPEAKER.id) is None
    controls = await _connected(
        harness, now_playing=NowPlaying(PlayState.PLAYING, title="Morning Light", app_name="Music")
    )

    assert controls.remote
    assert ui.MediaCommand.PLAY_PAUSE in controls.media
    assert controls.volume is ui.Volume.LEVEL
    assert controls.volume_level == 40.0
    assert controls.can_power
    assert controls.now_playing is not None
    assert controls.now_playing.title == "Morning Light"
    assert controls.now_playing.app == "Music"

    await harness.backend.disconnect(SPEAKER.id)
    assert harness.backend.controls(SPEAKER.id) is None
    assert ui.ControlsChanged(SPEAKER.id, None) in harness.events


async def test_pushed_updates_change_the_controls(harness: Harness) -> None:
    await _connected(harness)
    controller = harness.fake.controllers[SPEAKER.id]

    controller.push(NowPlaying(PlayState.PAUSED, title="Evening"))
    controller.push(PowerState.OFF)
    controller.push(55.0)
    controller.caps = frozenset({Capability.PLAY})
    controller.vol_control = VolumeControl.STEPS
    controller.push(None)

    controls = harness.backend.controls(SPEAKER.id)
    assert controls is not None
    assert controls.power == "off"
    assert controls.volume is ui.Volume.STEPS
    assert controls.volume_level is None
    assert controls.media == frozenset({ui.MediaCommand.PLAY_PAUSE})
    assert controls.now_playing is None  # NOW_PLAYING is no longer offered
    assert not controls.remote


async def test_commands_reach_the_device(harness: Harness) -> None:
    await _connected(harness)
    controller = harness.fake.controllers[SPEAKER.id]

    await harness.backend.press(SPEAKER.id, ui.RemoteKey.SELECT, ui.KeyAction.HOLD)
    await harness.backend.press(SPEAKER.id, ui.RemoteKey.VOLUME_UP, ui.KeyAction.TAP)
    await harness.backend.media(SPEAKER.id, ui.MediaCommand.NEXT)
    await harness.backend.media(SPEAKER.id, ui.MediaCommand.PLAY_PAUSE)
    await harness.backend.set_volume(SPEAKER.id, 30)
    await harness.backend.set_power(SPEAKER.id, False)

    assert controller.calls == [
        ("press", RemoteKey.SELECT, KeyAction.HOLD),
        ("volume_step", True),
        ("media", MediaCommand.NEXT),
        ("media", MediaCommand.PLAY_PAUSE),
        ("set_volume", 30),
        ("set_power", False),
    ]


@pytest.mark.parametrize(
    ("state", "expected"),
    [(PlayState.PLAYING, MediaCommand.PAUSE), (PlayState.PAUSED, MediaCommand.PLAY)],
)
async def test_play_pause_falls_back_to_play_or_pause(
    harness: Harness, state: PlayState, expected: MediaCommand
) -> None:
    caps = frozenset({Capability.PLAY, Capability.PAUSE, Capability.NOW_PLAYING})
    await _connected(harness, capabilities=caps, now_playing=NowPlaying(state))

    await harness.backend.media(SPEAKER.id, ui.MediaCommand.PLAY_PAUSE)

    assert harness.fake.controllers[SPEAKER.id].calls == [("media", expected)]


async def test_control_errors_are_worded_for_the_window(harness: Harness) -> None:
    with pytest.raises(ui.ControlError, match="isn't connected"):
        await harness.backend.press(SPEAKER.id, ui.RemoteKey.UP, ui.KeyAction.TAP)

    await _connected(harness, capabilities=frozenset({Capability.NOW_PLAYING}))
    with pytest.raises(ui.ControlError, match="can't do that"):
        await harness.backend.press(SPEAKER.id, ui.RemoteKey.UP, ui.KeyAction.TAP)

    harness.fake.controllers[SPEAKER.id].caps = ALL_CAPABILITIES
    harness.fake.controllers[SPEAKER.id].fail = ControlError("timed out talking to 192.0.2.10")
    with pytest.raises(ui.ControlError) as failed:
        await harness.backend.media(SPEAKER.id, ui.MediaCommand.NEXT)
    assert str(failed.value) == bridge.NO_RESPONSE


async def test_updates_for_unknown_devices_are_ignored(harness: Harness) -> None:
    harness.engine.bus.publish(PowerChanged("missing", PowerState.ON))
    harness.engine.bus.publish(ControlsUnavailable("missing"))
    assert not any(isinstance(e, ui.ControlsChanged) for e in harness.events)
