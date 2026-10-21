from __future__ import annotations

from typing import Any

import pytest
from pyatv import exceptions
from pyatv.const import (
    DeviceState,
    FeatureName,
    FeatureState,
    InputAction,
)
from pyatv.const import MediaType as PyatvMediaType
from pyatv.const import PowerState as PyatvPowerState
from pyatv.interface import App as PyatvApp
from pyatv.interface import ArtworkInfo, FeatureInfo, Playing

from tandem.engine.adapters.pyatv_control import PyatvController
from tandem.engine.control import (
    Capability,
    ControlError,
    ControlUpdate,
    KeyAction,
    MediaCommand,
    MediaType,
    PlayState,
    PowerState,
    RemoteKey,
    UnsupportedError,
    VolumeControl,
)


class _Features:
    def __init__(self, available: set[FeatureName]) -> None:
        self.available = available

    def get_feature(self, name: FeatureName) -> FeatureInfo:
        state = FeatureState.Available if name in self.available else FeatureState.Unavailable
        return FeatureInfo(state)


class _Recorder:
    """Any awaited method call is recorded as (name, args)."""

    def __init__(self, calls: list[tuple[str, tuple[Any, ...]]], prefix: str) -> None:
        self._calls = calls
        self._prefix = prefix

    def __getattr__(self, name: str) -> Any:
        async def call(*args: Any, **kwargs: Any) -> None:
            self._calls.append((f"{self._prefix}.{name}", args + tuple(kwargs.values())))

        return call


class _PushUpdater:
    def __init__(self) -> None:
        self.listener: Any = None
        self.active = False

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.active = False


class _Metadata:
    def __init__(self) -> None:
        self.app: PyatvApp | None = PyatvApp("Example Video", "com.example.video")
        self.playing_value = Playing(
            device_state=DeviceState.Playing,
            media_type=PyatvMediaType.Video,
            title="Invented Film",
            position=12,
            total_time=100,
        )

    async def playing(self) -> Playing:
        return self.playing_value

    async def artwork(self, width: int | None = None, height: int | None = None) -> ArtworkInfo:
        return ArtworkInfo(b"PNG", "image/png", width or 1, height or 1)


class _Audio:
    def __init__(self, calls: list[tuple[str, tuple[Any, ...]]]) -> None:
        self.volume = 35.0
        self.listener: Any = None
        self._calls = calls

    async def set_volume(self, level: float) -> None:
        self._calls.append(("audio.set_volume", (level,)))

    async def volume_up(self) -> None:
        self._calls.append(("audio.volume_up", ()))

    async def volume_down(self) -> None:
        self._calls.append(("audio.volume_down", ()))


class _Power:
    def __init__(self, calls: list[tuple[str, tuple[Any, ...]]]) -> None:
        self.power_state = PyatvPowerState.On
        self.listener: Any = None
        self._calls = calls

    async def turn_on(self) -> None:
        self._calls.append(("power.turn_on", ()))

    async def turn_off(self) -> None:
        self._calls.append(("power.turn_off", ()))


class _Apps:
    async def app_list(self) -> list[PyatvApp]:
        return [PyatvApp(None, "com.example.music"), PyatvApp("Example Video", "com.example.video")]

    async def launch_app(self, app_id: str) -> None:
        raise exceptions.NotSupportedError()


class _Keyboard:
    async def text_set(self, text: str) -> None:
        raise exceptions.ProtocolError("device said no")


class FakeAtv:
    def __init__(self, available: set[FeatureName]) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.features = _Features(available)
        self.remote_control = _Recorder(self.calls, "rc")
        self.push_updater = _PushUpdater()
        self.metadata = _Metadata()
        self.audio = _Audio(self.calls)
        self.power = _Power(self.calls)
        self.apps = _Apps()
        self.keyboard = _Keyboard()


EVERYTHING = set(FeatureName)


def _controller(available: set[FeatureName] = EVERYTHING) -> tuple[PyatvController, FakeAtv]:
    atv = FakeAtv(available)
    return PyatvController(atv), atv  # type: ignore[arg-type]


def test_capabilities_follow_features() -> None:
    controller, atv = _controller()
    assert controller.capabilities() == frozenset(Capability)
    atv.features.available = {
        FeatureName.Up,
        FeatureName.Down,
        FeatureName.Left,
        FeatureName.Right,
        FeatureName.Select,
        FeatureName.Menu,
        FeatureName.PlayPause,
        FeatureName.PowerState,  # without TurnOn/TurnOff: no POWER
    }
    assert controller.capabilities() == {Capability.REMOTE, Capability.PLAY_PAUSE}


@pytest.mark.parametrize(
    ("available", "expected", "level"),
    [
        ({FeatureName.Volume, FeatureName.SetVolume}, VolumeControl.LEVEL, 35.0),
        ({FeatureName.VolumeUp, FeatureName.VolumeDown}, VolumeControl.STEPS, None),
        ({FeatureName.VolumeUp}, VolumeControl.NONE, None),
        (set[FeatureName](), VolumeControl.NONE, None),
    ],
)
def test_volume_control(
    available: set[FeatureName], expected: VolumeControl, level: float | None
) -> None:
    controller, _ = _controller(available)
    assert controller.volume_control() is expected
    assert controller.volume() == level


def test_power_state() -> None:
    controller, atv = _controller()
    assert controller.power() is PowerState.ON
    atv.power.power_state = PyatvPowerState.Unknown
    assert controller.power() is PowerState.UNKNOWN
    atv.features.available = set()
    assert controller.power() is PowerState.UNKNOWN


async def test_keys_and_media_map_to_pyatv() -> None:
    controller, atv = _controller()
    await controller.press(RemoteKey.SELECT, KeyAction.DOUBLE_TAP)
    await controller.press(RemoteKey.TOP_MENU, KeyAction.TAP)
    await controller.media(MediaCommand.SKIP_FORWARD)
    await controller.seek(41.6)
    await controller.set_volume(20)
    await controller.volume_step(True)
    await controller.volume_step(False)
    await controller.set_power(True)
    await controller.set_power(False)
    assert atv.calls == [
        ("rc.select", (InputAction.DoubleTap,)),
        ("rc.top_menu", ()),
        ("rc.skip_forward", ()),
        ("rc.set_position", (42,)),
        ("audio.set_volume", (20,)),
        ("audio.volume_up", ()),
        ("audio.volume_down", ()),
        ("power.turn_on", ()),
        ("power.turn_off", ()),
    ]


async def test_every_key_and_command_has_a_mapping() -> None:
    controller, atv = _controller()
    for key in RemoteKey:
        await controller.press(key, KeyAction.TAP)
    for command in MediaCommand:
        await controller.media(command)
    assert len(atv.calls) == len(RemoteKey) + len(MediaCommand)


async def test_now_playing_conversion() -> None:
    controller, atv = _controller()
    now = await controller.now_playing()
    assert now.state is PlayState.PLAYING
    assert now.media_type is MediaType.VIDEO
    assert now.title == "Invented Film"
    assert (now.position, now.total_time) == (12.0, 100.0)
    assert (now.app_name, now.app_id) == ("Example Video", "com.example.video")
    atv.metadata.app = None
    atv.metadata.playing_value = Playing()
    now = await controller.now_playing()
    assert now.state is PlayState.IDLE
    assert now.media_type is MediaType.UNKNOWN
    assert now.app_name is None
    assert now.position is None


async def test_artwork_apps_and_errors() -> None:
    controller, _ = _controller()
    art = await controller.artwork(64, 64)
    assert art is not None
    assert (art.mimetype, art.width) == ("image/png", 64)
    apps = await controller.apps()
    assert [(a.id, a.name) for a in apps] == [
        ("com.example.music", "com.example.music"),  # no name: fall back to the id
        ("com.example.video", "Example Video"),
    ]
    with pytest.raises(UnsupportedError):
        await controller.launch("com.example.video")
    with pytest.raises(ControlError, match="ProtocolError"):
        await controller.set_text("x")


def test_push_updates_are_converted() -> None:
    controller, atv = _controller()
    updates: list[ControlUpdate] = []
    controller.start(updates.append)
    assert atv.push_updater.active
    listener = atv.push_updater.listener
    listener.playstatus_update(None, Playing(device_state=DeviceState.Paused))
    listener.playstatus_error(None, OSError())
    atv.power.listener.powerstate_update(PyatvPowerState.On, PyatvPowerState.Off)
    atv.audio.listener.volume_update(10.0, 20.0)
    atv.audio.listener.outputdevices_update([], [])
    atv.audio.listener.volume_device_update(None, 1.0, 2.0)
    assert updates[0].state is PlayState.PAUSED  # type: ignore[union-attr]
    assert updates[1:] == [None, PowerState.OFF, 20.0, None]
    controller.stop()
    assert not atv.push_updater.active
    controller.stop()  # twice is harmless


def test_no_push_updates_without_the_feature() -> None:
    controller, atv = _controller(set())
    controller.start(lambda _update: None)
    assert not atv.push_updater.active
    controller.stop()


def test_closed_connection_reports_nothing() -> None:
    class Closed(FakeAtv):
        @property
        def features(self) -> Any:  # pyright: ignore[reportIncompatibleVariableOverride]
            raise exceptions.BlockedStateError("features is blocked")

        @features.setter
        def features(self, _value: Any) -> None:
            pass

    atv = Closed(EVERYTHING)
    controller = PyatvController(atv)  # type: ignore[arg-type]
    assert controller.capabilities() == frozenset()
    assert controller.volume_control() is VolumeControl.NONE
