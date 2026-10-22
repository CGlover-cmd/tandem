"""pyatv-backed `Controller`: remote keys, media, now-playing, power, volume, apps and text."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pyatv import exceptions
from pyatv.const import DeviceState, FeatureName, FeatureState, InputAction, KeyboardFocusState
from pyatv.const import MediaType as PyatvMediaType
from pyatv.const import PowerState as PyatvPowerState
from pyatv.interface import (
    AppleTV,
    AudioListener,
    KeyboardListener,
    Playing,
    PowerListener,
    PushListener,
)

from tandem.engine.control import (
    App,
    Artwork,
    Capability,
    ControlError,
    ControlUpdate,
    KeyAction,
    KeyboardFocus,
    MediaCommand,
    MediaType,
    NoTextFieldError,
    NowPlaying,
    PlayState,
    PowerState,
    RemoteKey,
    UnsupportedError,
    VolumeControl,
)

T = TypeVar("T")

# A capability is offered when every listed pyatv feature is available.
_CAPABILITY_FEATURES: dict[Capability, tuple[FeatureName, ...]] = {
    Capability.REMOTE: (
        FeatureName.Up,
        FeatureName.Down,
        FeatureName.Left,
        FeatureName.Right,
        FeatureName.Select,
        FeatureName.Menu,
    ),
    Capability.PLAY: (FeatureName.Play,),
    Capability.PAUSE: (FeatureName.Pause,),
    Capability.PLAY_PAUSE: (FeatureName.PlayPause,),
    Capability.STOP: (FeatureName.Stop,),
    Capability.NEXT: (FeatureName.Next,),
    Capability.PREVIOUS: (FeatureName.Previous,),
    Capability.SKIP_FORWARD: (FeatureName.SkipForward,),
    Capability.SKIP_BACKWARD: (FeatureName.SkipBackward,),
    Capability.SEEK: (FeatureName.SetPosition,),
    Capability.NOW_PLAYING: (FeatureName.PushUpdates,),
    Capability.ARTWORK: (FeatureName.Artwork,),
    Capability.POWER: (FeatureName.PowerState, FeatureName.TurnOn, FeatureName.TurnOff),
    Capability.APPS: (FeatureName.AppList, FeatureName.LaunchApp),
    Capability.TEXT_ENTRY: (FeatureName.TextSet,),
    Capability.CHANNELS: (FeatureName.ChannelUp, FeatureName.ChannelDown),
    Capability.SCREENSAVER: (FeatureName.Screensaver,),
}

_ACTIONS = {
    KeyAction.TAP: InputAction.SingleTap,
    KeyAction.DOUBLE_TAP: InputAction.DoubleTap,
    KeyAction.HOLD: InputAction.Hold,
}

_PLAY_STATES = {
    DeviceState.Idle: PlayState.IDLE,
    DeviceState.Loading: PlayState.LOADING,
    DeviceState.Paused: PlayState.PAUSED,
    DeviceState.Playing: PlayState.PLAYING,
    DeviceState.Stopped: PlayState.STOPPED,
    DeviceState.Seeking: PlayState.SEEKING,
}

_MEDIA_TYPES = {
    PyatvMediaType.Video: MediaType.VIDEO,
    PyatvMediaType.Music: MediaType.MUSIC,
    PyatvMediaType.TV: MediaType.TV,
}

_POWER = {PyatvPowerState.On: PowerState.ON, PyatvPowerState.Off: PowerState.OFF}


def now_playing_from(playing: Playing, app_name: str | None, app_id: str | None) -> NowPlaying:
    return NowPlaying(
        state=_PLAY_STATES.get(playing.device_state, PlayState.UNKNOWN),
        media_type=_MEDIA_TYPES.get(playing.media_type, MediaType.UNKNOWN),
        title=playing.title,
        artist=playing.artist,
        album=playing.album,
        series=playing.series_name,
        season=playing.season_number,
        episode=playing.episode_number,
        position=float(playing.position) if playing.position is not None else None,
        total_time=float(playing.total_time) if playing.total_time is not None else None,
        app_name=app_name,
        app_id=app_id,
    )


async def _guard(call: Awaitable[T], what: str) -> T:
    """Run a pyatv call, turning its errors into ControlError (type names only)."""
    try:
        return await call
    except exceptions.NotSupportedError:
        raise UnsupportedError(what) from None
    except (exceptions.ProtocolError, exceptions.ConnectionLostError, OSError, TimeoutError) as exc:
        raise ControlError(f"{what} failed ({type(exc).__name__})") from exc


class _Listeners(PushListener, PowerListener, AudioListener, KeyboardListener):
    def __init__(self, controller: PyatvController, on_update: Callable[[ControlUpdate], None]):
        self._controller = controller
        self._on_update = on_update

    def playstatus_update(self, updater: Any, playstatus: Playing) -> None:
        self._on_update(self._controller.convert(playstatus))

    def playstatus_error(self, updater: Any, exception: Exception) -> None:
        self._on_update(None)

    def powerstate_update(self, old_state: PyatvPowerState, new_state: PyatvPowerState) -> None:
        self._on_update(_POWER.get(new_state, PowerState.UNKNOWN))

    def volume_update(self, old_level: float, new_level: float) -> None:
        self._on_update(float(new_level))

    def outputdevices_update(self, old_devices: Any, new_devices: Any) -> None:
        self._on_update(None)  # output changes can change volume control

    def volume_device_update(self, output_device: Any, old_level: float, new_level: float) -> None:
        return None

    def focusstate_update(
        self, old_state: KeyboardFocusState, new_state: KeyboardFocusState
    ) -> None:
        self._on_update(KeyboardFocus(new_state == KeyboardFocusState.Focused))


class PyatvController:
    def __init__(self, atv: AppleTV) -> None:
        self._atv = atv
        self._listeners: _Listeners | None = None

    # --- state ---------------------------------------------------------------------

    def _available(self, *names: FeatureName) -> bool:
        try:
            features = self._atv.features  # blocked once the connection has closed
            return all(features.get_feature(n).state == FeatureState.Available for n in names)
        except Exception:
            return False

    def capabilities(self) -> frozenset[Capability]:
        return frozenset(
            capability
            for capability, names in _CAPABILITY_FEATURES.items()
            if self._available(*names)
        )

    def volume_control(self) -> VolumeControl:
        if self._available(FeatureName.SetVolume):
            return VolumeControl.LEVEL
        if self._available(FeatureName.VolumeUp, FeatureName.VolumeDown):
            return VolumeControl.STEPS
        return VolumeControl.NONE

    def volume(self) -> float | None:
        if not self._available(FeatureName.Volume, FeatureName.SetVolume):
            return None
        try:
            return float(self._atv.audio.volume)
        except exceptions.NotSupportedError:
            return None

    def power(self) -> PowerState:
        if not self._available(FeatureName.PowerState):
            return PowerState.UNKNOWN
        return _POWER.get(self._atv.power.power_state, PowerState.UNKNOWN)

    def keyboard_focused(self) -> bool:
        if not self._available(FeatureName.TextFocusState):
            return False
        try:
            return self._atv.keyboard.text_focus_state == KeyboardFocusState.Focused
        except Exception:  # blocked once the connection has closed
            return False

    def convert(self, playing: Playing) -> NowPlaying:
        app_name = app_id = None
        if self._available(FeatureName.App):
            try:
                app = self._atv.metadata.app
            except exceptions.NotSupportedError:
                app = None
            if app is not None:
                app_name, app_id = app.name, app.identifier
        return now_playing_from(playing, app_name, app_id)

    # --- commands ------------------------------------------------------------------

    async def press(self, key: RemoteKey, action: KeyAction) -> None:
        rc = self._atv.remote_control
        pyatv_action = _ACTIONS[action]
        calls: dict[RemoteKey, Callable[[], Awaitable[None]]] = {
            RemoteKey.UP: lambda: rc.up(pyatv_action),
            RemoteKey.DOWN: lambda: rc.down(pyatv_action),
            RemoteKey.LEFT: lambda: rc.left(pyatv_action),
            RemoteKey.RIGHT: lambda: rc.right(pyatv_action),
            RemoteKey.SELECT: lambda: rc.select(pyatv_action),
            RemoteKey.MENU: lambda: rc.menu(pyatv_action),
            RemoteKey.HOME: lambda: rc.home(pyatv_action),
            RemoteKey.TOP_MENU: rc.top_menu,
            RemoteKey.PLAY_PAUSE: rc.play_pause,
            RemoteKey.VOLUME_UP: rc.volume_up,
            RemoteKey.VOLUME_DOWN: rc.volume_down,
            RemoteKey.CHANNEL_UP: rc.channel_up,
            RemoteKey.CHANNEL_DOWN: rc.channel_down,
            RemoteKey.SCREENSAVER: rc.screensaver,
        }
        await _guard(calls[key](), key.value)

    async def media(self, command: MediaCommand) -> None:
        rc = self._atv.remote_control
        calls: dict[MediaCommand, Callable[[], Awaitable[None]]] = {
            MediaCommand.PLAY: rc.play,
            MediaCommand.PAUSE: rc.pause,
            MediaCommand.PLAY_PAUSE: rc.play_pause,
            MediaCommand.STOP: rc.stop,
            MediaCommand.NEXT: rc.next,
            MediaCommand.PREVIOUS: rc.previous,
            MediaCommand.SKIP_FORWARD: rc.skip_forward,
            MediaCommand.SKIP_BACKWARD: rc.skip_backward,
        }
        await _guard(calls[command](), command.value)

    async def seek(self, position: float) -> None:
        await _guard(self._atv.remote_control.set_position(round(position)), "seek")

    async def set_volume(self, level: float) -> None:
        await _guard(self._atv.audio.set_volume(level), "volume")

    async def volume_step(self, up: bool) -> None:
        audio = self._atv.audio
        await _guard(audio.volume_up() if up else audio.volume_down(), "volume")

    async def set_power(self, on: bool) -> None:
        power = self._atv.power
        await _guard(power.turn_on() if on else power.turn_off(), "power")

    async def now_playing(self) -> NowPlaying:
        return self.convert(await _guard(self._atv.metadata.playing(), "now playing"))

    async def artwork(self, width: int | None, height: int | None) -> Artwork | None:
        info = await _guard(self._atv.metadata.artwork(width=width, height=height), "artwork")
        if info is None:
            return None
        return Artwork(info.bytes, info.mimetype, info.width, info.height)

    async def apps(self) -> list[App]:
        found = await _guard(self._atv.apps.app_list(), "apps")
        return [App(app.identifier, app.name or app.identifier) for app in found]

    async def launch(self, app_id: str) -> None:
        await _guard(self._atv.apps.launch_app(app_id), "launch app")

    async def set_text(self, text: str) -> None:
        # With no text field selected, the Apple TV ignores typed text and pyatv reports
        # nothing, so check first and say so.
        if not self.keyboard_focused():
            raise NoTextFieldError()
        await _guard(self._atv.keyboard.text_set(text), "text entry")

    # --- push updates --------------------------------------------------------------

    def start(self, on_update: Callable[[ControlUpdate], None]) -> None:
        listeners = _Listeners(self, on_update)
        self._listeners = listeners  # pyatv holds listeners weakly
        self._atv.power.listener = listeners
        self._atv.audio.listener = listeners
        if self._available(FeatureName.TextFocusState):
            self._atv.keyboard.listener = listeners
        if self._available(FeatureName.PushUpdates):
            self._atv.push_updater.listener = listeners
            self._atv.push_updater.start()

    def stop(self) -> None:
        if self._listeners is None:
            return
        try:
            if self._atv.push_updater.active:
                self._atv.push_updater.stop()
        except exceptions.NotSupportedError:
            pass
        self._listeners = None
