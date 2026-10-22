from __future__ import annotations

import asyncio

import pytest

from conftest import FakeBackend, ManualSleep, make_device
from tandem.engine.control import (
    CapabilitiesChanged,
    Capability,
    ControlError,
    ControlEvent,
    ControlsAvailable,
    ControlsUnavailable,
    KeyAction,
    KeyboardChanged,
    KeyboardFocus,
    MediaCommand,
    MediaType,
    NotConnectedError,
    NowPlaying,
    NowPlayingChanged,
    PlayState,
    PowerChanged,
    PowerState,
    RemoteKey,
    UnsupportedError,
    VolumeChanged,
    VolumeControl,
)
from tandem.engine.models import DeviceKind, Service
from tandem.engine.service import Engine

TV = make_device(
    id="AA:BB:CC:00:00:02",
    name="Den TV",
    kind=DeviceKind.APPLE_TV,
    model="Apple TV 4K (gen 2)",
    services=frozenset({Service.COMPANION, Service.AIRPLAY}),
)
PLAYING = NowPlaying(state=PlayState.PLAYING, media_type=MediaType.VIDEO, title="Invented Film")


async def _connected(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> tuple[Engine, list[ControlEvent]]:
    engine = Engine(backend, sleep=manual_sleep)
    events: list[ControlEvent] = []
    engine.bus.subscribe(ControlEvent, events.append)
    ready = asyncio.ensure_future(engine.bus.wait_for(ControlsAvailable, timeout=1))
    await engine.connect(TV.id, timeout=1)
    await ready
    return engine, events


@pytest.fixture
def backend() -> FakeBackend:
    backend = FakeBackend([TV])
    backend.controller_options = {"now_playing": PLAYING}
    return backend


async def test_controls_announce_their_starting_state(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    engine, events = await _connected(backend, manual_sleep)
    (available,) = [e for e in events if isinstance(e, ControlsAvailable)]
    assert available.device_id == TV.id
    assert available.status.now_playing == PLAYING
    assert available.status.volume == 40.0
    assert available.status.power is PowerState.ON
    controls = engine.controls(TV.id)
    assert controls.connected
    assert controls.status().now_playing == PLAYING
    await engine.close()


async def test_commands_reach_the_device(backend: FakeBackend, manual_sleep: ManualSleep) -> None:
    engine, _ = await _connected(backend, manual_sleep)
    controls = engine.controls(TV.id)
    await controls.press(RemoteKey.SELECT)
    await controls.press(RemoteKey.HOME, KeyAction.HOLD)
    await controls.media(MediaCommand.PAUSE)
    await controls.seek(30)
    await controls.set_volume(55)
    await controls.volume_up()
    await controls.press(RemoteKey.VOLUME_DOWN)
    await controls.set_power(False)
    assert await controls.now_playing() == PLAYING
    art = await controls.artwork(100, 100)
    assert art is not None
    assert art.mimetype == "image/png"
    assert [a.id for a in await controls.apps()] == ["com.example.video"]
    await controls.launch("com.example.video")
    await controls.set_text("search words")
    assert backend.controllers[TV.id].calls == [
        ("press", RemoteKey.SELECT, KeyAction.TAP),
        ("press", RemoteKey.HOME, KeyAction.HOLD),
        ("media", MediaCommand.PAUSE),
        ("seek", 30),
        ("set_volume", 55),
        ("volume_step", True),
        ("volume_step", False),
        ("set_power", False),
        ("artwork", 100, 100),
        ("apps",),
        ("launch", "com.example.video"),
        ("set_text", "search words"),
    ]
    await engine.close()


async def test_missing_capabilities_are_refused_before_sending(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    backend.controller_options = {
        "capabilities": frozenset({Capability.REMOTE}),
        "volume_control": VolumeControl.NONE,
    }
    engine, _ = await _connected(backend, manual_sleep)
    controls = engine.controls(TV.id)
    for call in (
        controls.media(MediaCommand.PLAY),
        controls.seek(1),
        controls.set_volume(10),
        controls.volume_up(),
        controls.press(RemoteKey.VOLUME_UP),
        controls.press(RemoteKey.PLAY_PAUSE),
        controls.press(RemoteKey.CHANNEL_UP),
        controls.press(RemoteKey.SCREENSAVER),
        controls.set_power(True),
        controls.now_playing(),
        controls.artwork(),
        controls.apps(),
        controls.launch("x"),
        controls.set_text("x"),
        controls.press(RemoteKey.TOP_MENU, KeyAction.HOLD),
    ):
        with pytest.raises(UnsupportedError):
            await call
    await controls.press(RemoteKey.UP)  # REMOTE is offered
    assert backend.controllers[TV.id].calls == [("press", RemoteKey.UP, KeyAction.TAP)]
    assert controls.status().volume is None
    await engine.close()


async def test_volume_steps_only(backend: FakeBackend, manual_sleep: ManualSleep) -> None:
    backend.controller_options = {"volume_control": VolumeControl.STEPS}
    engine, _ = await _connected(backend, manual_sleep)
    controls = engine.controls(TV.id)
    await controls.volume_down()
    with pytest.raises(UnsupportedError, match="volume level"):
        await controls.set_volume(20)
    assert controls.status().volume is None
    await engine.close()


async def test_bad_values(backend: FakeBackend, manual_sleep: ManualSleep) -> None:
    engine, _ = await _connected(backend, manual_sleep)
    controls = engine.controls(TV.id)
    with pytest.raises(ValueError, match="volume"):
        await controls.set_volume(150)
    with pytest.raises(ValueError, match="position"):
        await controls.seek(-1)
    await engine.close()


async def test_not_connected(backend: FakeBackend) -> None:
    engine = Engine(backend)
    controls = engine.controls(TV.id)
    assert not controls.connected
    assert controls.status().capabilities == frozenset()
    with pytest.raises(NotConnectedError):
        await controls.press(RemoteKey.UP)


async def test_pushes_become_events(backend: FakeBackend, manual_sleep: ManualSleep) -> None:
    engine, events = await _connected(backend, manual_sleep)
    controller = backend.controllers[TV.id]
    paused = NowPlaying(state=PlayState.PAUSED)
    controller.push(paused)
    controller.push(PowerState.OFF)
    controller.push(25.0)
    controller.caps = frozenset({Capability.REMOTE})
    controller.push(None)
    controller.push(None)  # no change: no second event
    pushed = [e for e in events if not isinstance(e, ControlsAvailable)]
    assert pushed == [
        NowPlayingChanged(TV.id, paused),
        PowerChanged(TV.id, PowerState.OFF),
        VolumeChanged(TV.id, 25.0),
        CapabilitiesChanged(TV.id, frozenset({Capability.REMOTE}), VolumeControl.LEVEL),
    ]
    assert engine.controls(TV.id).status().now_playing == paused
    await engine.close()


async def test_keyboard_focus_becomes_events(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    engine, events = await _connected(backend, manual_sleep)
    controller = backend.controllers[TV.id]
    assert not engine.controls(TV.id).status().keyboard
    controller.push(KeyboardFocus(True))
    controller.push(KeyboardFocus(True))  # no change: no second event
    controller.keyboard = True
    assert engine.controls(TV.id).status().keyboard
    controller.push(KeyboardFocus(False))
    pushed = [e for e in events if not isinstance(e, ControlsAvailable)]
    assert pushed == [KeyboardChanged(TV.id, True), KeyboardChanged(TV.id, False)]
    await engine.close()


async def test_keyboard_already_showing_is_announced(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    backend.controller_options = {"now_playing": PLAYING, "keyboard": True}
    engine, events = await _connected(backend, manual_sleep)
    available = [e for e in events if isinstance(e, ControlsAvailable)]
    assert available[0].status.keyboard
    await engine.close()


async def test_disconnect_drops_controls(backend: FakeBackend, manual_sleep: ManualSleep) -> None:
    engine, events = await _connected(backend, manual_sleep)
    controller = backend.controllers[TV.id]
    await engine.disconnect(TV.id)
    assert controller.stopped
    assert isinstance(events[-1], ControlsUnavailable)
    controller.push(PowerState.OFF)  # a late push from the old connection is ignored
    assert not any(isinstance(e, PowerChanged) for e in events)
    with pytest.raises(NotConnectedError):
        await engine.controls(TV.id).press(RemoteKey.UP)


async def test_reconnect_gets_a_fresh_controller(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    engine, _ = await _connected(backend, manual_sleep)
    first = backend.controllers[TV.id]
    backend.lost_callbacks[TV.id](ConnectionResetError())
    await manual_sleep.until(1)
    assert first.stopped
    ready = asyncio.ensure_future(engine.bus.wait_for(ControlsAvailable, timeout=1))
    manual_sleep.release()
    await ready
    assert backend.controllers[TV.id] is not first
    await engine.controls(TV.id).press(RemoteKey.UP)
    assert backend.controllers[TV.id].calls == [("press", RemoteKey.UP, KeyAction.TAP)]
    await engine.close()


async def test_now_playing_read_failure_still_announces(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    backend.controller_options = {"fail": ControlError("now playing failed (OSError)")}
    engine, events = await _connected(backend, manual_sleep)
    (available,) = [e for e in events if isinstance(e, ControlsAvailable)]
    assert available.status.now_playing == NowPlaying()
    with pytest.raises(ControlError):
        await engine.controls(TV.id).press(RemoteKey.UP)
    await engine.close()


async def test_devices_without_controls(manual_sleep: ManualSleep) -> None:
    class NoControls(FakeBackend):
        def controller(self, link: object) -> None:
            return None

    backend = NoControls([TV])
    engine = Engine(backend, sleep=manual_sleep)
    await engine.connect(TV.id, timeout=1)
    await asyncio.sleep(0)
    assert not engine.controls(TV.id).connected
    await engine.close()


async def test_push_while_closing_is_ignored(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    engine, events = await _connected(backend, manual_sleep)
    controller = backend.controllers[TV.id]

    def broken() -> frozenset[Capability]:
        raise RuntimeError("connection closing")

    controller.capabilities = broken  # type: ignore[method-assign]
    controller.push(30.0)
    assert isinstance(events[-1], VolumeChanged)
    await engine.close()
