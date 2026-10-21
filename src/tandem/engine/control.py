"""Remote control, media control and now-playing (Phase 3), protocol-agnostic.

A backend turns an open connection into a `Controller` (the pyatv one is in `adapters`). The
engine attaches one to each connected device and republishes what it pushes as events, so the
UI never polls. `Capability` says what a device offers right now. On an Apple TV this changes
with what's playing, so the UI should follow `CapabilitiesChanged`, not read it once.

Volume differs by device and setup. `VolumeControl` says what's possible: an exact level,
up/down steps only (an Apple TV passing volume to the TV over HDMI-CEC), or nothing (the
Apple TV with no volume path; the UI should hide the slider and point at the TV remote).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from tandem.engine.events import Event


class RemoteKey(Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    SELECT = "select"
    MENU = "menu"  # "back" on the Siri Remote
    HOME = "home"
    TOP_MENU = "top_menu"
    PLAY_PAUSE = "play_pause"
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    CHANNEL_UP = "channel_up"
    CHANNEL_DOWN = "channel_down"
    SCREENSAVER = "screensaver"


class KeyAction(Enum):
    TAP = "tap"
    DOUBLE_TAP = "double_tap"
    HOLD = "hold"


# Keys that accept DOUBLE_TAP and HOLD; the rest only take a plain tap.
ACTION_KEYS = frozenset(
    {
        RemoteKey.UP,
        RemoteKey.DOWN,
        RemoteKey.LEFT,
        RemoteKey.RIGHT,
        RemoteKey.SELECT,
        RemoteKey.MENU,
        RemoteKey.HOME,
    }
)


class MediaCommand(Enum):
    PLAY = "play"
    PAUSE = "pause"
    PLAY_PAUSE = "play_pause"
    STOP = "stop"
    NEXT = "next"
    PREVIOUS = "previous"
    SKIP_FORWARD = "skip_forward"
    SKIP_BACKWARD = "skip_backward"


class Capability(Enum):
    """Something a device can do at the moment."""

    REMOTE = "remote"  # arrow keys, select, menu, home
    PLAY = "play"
    PAUSE = "pause"
    PLAY_PAUSE = "play_pause"
    STOP = "stop"
    NEXT = "next"
    PREVIOUS = "previous"
    SKIP_FORWARD = "skip_forward"
    SKIP_BACKWARD = "skip_backward"
    SEEK = "seek"
    NOW_PLAYING = "now_playing"
    ARTWORK = "artwork"
    POWER = "power"  # read and change power state
    APPS = "apps"  # list and launch apps
    TEXT_ENTRY = "text_entry"
    CHANNELS = "channels"
    SCREENSAVER = "screensaver"


MEDIA_CAPABILITY = {
    MediaCommand.PLAY: Capability.PLAY,
    MediaCommand.PAUSE: Capability.PAUSE,
    MediaCommand.PLAY_PAUSE: Capability.PLAY_PAUSE,
    MediaCommand.STOP: Capability.STOP,
    MediaCommand.NEXT: Capability.NEXT,
    MediaCommand.PREVIOUS: Capability.PREVIOUS,
    MediaCommand.SKIP_FORWARD: Capability.SKIP_FORWARD,
    MediaCommand.SKIP_BACKWARD: Capability.SKIP_BACKWARD,
}


def key_capability(key: RemoteKey) -> Capability | None:
    """The capability a key needs; volume keys are checked against `VolumeControl` instead."""
    if key in (RemoteKey.VOLUME_UP, RemoteKey.VOLUME_DOWN):
        return None
    if key is RemoteKey.PLAY_PAUSE:
        return Capability.PLAY_PAUSE
    if key in (RemoteKey.CHANNEL_UP, RemoteKey.CHANNEL_DOWN):
        return Capability.CHANNELS
    if key is RemoteKey.SCREENSAVER:
        return Capability.SCREENSAVER
    return Capability.REMOTE


class VolumeControl(Enum):
    LEVEL = "level"  # an exact level, 0 to 100
    STEPS = "steps"  # up and down only, no level
    NONE = "none"


class PlayState(Enum):
    IDLE = "idle"
    LOADING = "loading"
    PAUSED = "paused"
    PLAYING = "playing"
    STOPPED = "stopped"
    SEEKING = "seeking"
    UNKNOWN = "unknown"


class MediaType(Enum):
    VIDEO = "video"
    MUSIC = "music"
    TV = "tv"
    UNKNOWN = "unknown"


class PowerState(Enum):
    ON = "on"
    OFF = "off"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class NowPlaying:
    """What's playing. Titles are personal: don't log them, and hide them in shared output."""

    state: PlayState = PlayState.IDLE
    media_type: MediaType = MediaType.UNKNOWN
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    series: str | None = None
    season: int | None = None
    episode: int | None = None
    position: float | None = None
    """Seconds into the item."""
    total_time: float | None = None
    """Length of the item in seconds."""
    app_name: str | None = None
    app_id: str | None = None


@dataclass(frozen=True, slots=True)
class Artwork:
    data: bytes
    mimetype: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class App:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class ControlStatus:
    """Everything the UI needs to draw a device's controls."""

    capabilities: frozenset[Capability] = frozenset[Capability]()
    volume_control: VolumeControl = VolumeControl.NONE
    volume: float | None = None
    """0 to 100 when `volume_control` is LEVEL, else None."""
    power: PowerState = PowerState.UNKNOWN
    now_playing: NowPlaying = NowPlaying()


# --- Events ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ControlEvent(Event):
    device_id: str


@dataclass(frozen=True, slots=True)
class NowPlayingChanged(ControlEvent):
    now_playing: NowPlaying


@dataclass(frozen=True, slots=True)
class CapabilitiesChanged(ControlEvent):
    capabilities: frozenset[Capability]
    volume_control: VolumeControl


@dataclass(frozen=True, slots=True)
class PowerChanged(ControlEvent):
    power: PowerState


@dataclass(frozen=True, slots=True)
class VolumeChanged(ControlEvent):
    volume: float


@dataclass(frozen=True, slots=True)
class ControlsAvailable(ControlEvent):
    """The device connected and its controls are ready, with their starting state."""

    status: ControlStatus


@dataclass(frozen=True, slots=True)
class ControlsUnavailable(ControlEvent):
    """The device disconnected; drop its controls until ControlsAvailable."""


# --- Errors ---------------------------------------------------------------------------


class ControlError(Exception):
    """A control command couldn't run. `str()` is safe to show; it holds no private data."""


class NotConnectedError(ControlError):
    def __init__(self) -> None:
        super().__init__("not connected")


class UnsupportedError(ControlError):
    """The device doesn't offer this right now (see its capabilities)."""

    def __init__(self, what: str) -> None:
        super().__init__(f"not supported right now: {what}")
        self.what = what


# --- What a backend provides -----------------------------------------------------------

ControlUpdate = NowPlaying | PowerState | float | None
"""Pushed by a controller: new now-playing, power state, volume level, or None when only
capabilities may have changed."""


class Controller(Protocol):
    """Controls on one open connection. Methods raise ControlError subclasses."""

    def capabilities(self) -> frozenset[Capability]: ...
    def volume_control(self) -> VolumeControl: ...
    def volume(self) -> float | None: ...
    def power(self) -> PowerState: ...

    async def press(self, key: RemoteKey, action: KeyAction) -> None: ...
    async def media(self, command: MediaCommand) -> None: ...
    async def seek(self, position: float) -> None: ...
    async def set_volume(self, level: float) -> None: ...
    async def volume_step(self, up: bool) -> None: ...
    async def set_power(self, on: bool) -> None: ...
    async def now_playing(self) -> NowPlaying: ...
    async def artwork(self, width: int | None, height: int | None) -> Artwork | None: ...
    async def apps(self) -> list[App]: ...
    async def launch(self, app_id: str) -> None: ...
    async def set_text(self, text: str) -> None: ...

    def start(self, on_update: Callable[[ControlUpdate], None]) -> None:
        """Begin pushing updates. Stopped when the connection closes."""

    def stop(self) -> None: ...


# --- The facade the UI calls -----------------------------------------------------------


class DeviceControls:
    """Controls for one device, valid across reconnects (it looks up the live controller on
    every call). Checks capabilities first, so the UI gets UnsupportedError rather than a
    protocol error."""

    def __init__(
        self,
        device_id: str,
        controller: Callable[[], Controller | None],
        last_now_playing: Callable[[], NowPlaying],
    ) -> None:
        self.device_id = device_id
        self._controller = controller
        self._last_now_playing = last_now_playing

    def _live(self) -> Controller:
        controller = self._controller()
        if controller is None:
            raise NotConnectedError()
        return controller

    def _require(self, controller: Controller, capability: Capability) -> None:
        if capability not in controller.capabilities():
            raise UnsupportedError(capability.value)

    @property
    def connected(self) -> bool:
        return self._controller() is not None

    def status(self) -> ControlStatus:
        controller = self._controller()
        if controller is None:
            return ControlStatus()
        return ControlStatus(
            capabilities=controller.capabilities(),
            volume_control=controller.volume_control(),
            volume=controller.volume(),
            power=controller.power(),
            now_playing=self._last_now_playing(),
        )

    async def press(self, key: RemoteKey, action: KeyAction = KeyAction.TAP) -> None:
        controller = self._live()
        if action is not KeyAction.TAP and key not in ACTION_KEYS:
            raise UnsupportedError(f"{action.value} on {key.value}")
        if key in (RemoteKey.VOLUME_UP, RemoteKey.VOLUME_DOWN):
            await self._volume_step(controller, up=key is RemoteKey.VOLUME_UP)
            return
        needed = key_capability(key)
        if needed is not None:
            self._require(controller, needed)
        await controller.press(key, action)

    async def media(self, command: MediaCommand) -> None:
        controller = self._live()
        self._require(controller, MEDIA_CAPABILITY[command])
        await controller.media(command)

    async def seek(self, position: float) -> None:
        if position < 0:
            raise ValueError("position must be >= 0")
        controller = self._live()
        self._require(controller, Capability.SEEK)
        await controller.seek(position)

    async def set_volume(self, level: float) -> None:
        if not 0 <= level <= 100:
            raise ValueError("volume must be between 0 and 100")
        controller = self._live()
        if controller.volume_control() is not VolumeControl.LEVEL:
            raise UnsupportedError("volume level")
        await controller.set_volume(level)

    async def volume_up(self) -> None:
        await self._volume_step(self._live(), up=True)

    async def volume_down(self) -> None:
        await self._volume_step(self._live(), up=False)

    async def _volume_step(self, controller: Controller, *, up: bool) -> None:
        if controller.volume_control() is VolumeControl.NONE:
            raise UnsupportedError("volume")
        await controller.volume_step(up)

    async def set_power(self, on: bool) -> None:
        controller = self._live()
        self._require(controller, Capability.POWER)
        await controller.set_power(on)

    async def now_playing(self) -> NowPlaying:
        controller = self._live()
        self._require(controller, Capability.NOW_PLAYING)
        return await controller.now_playing()

    async def artwork(self, width: int | None = None, height: int | None = None) -> Artwork | None:
        controller = self._live()
        self._require(controller, Capability.ARTWORK)
        return await controller.artwork(width, height)

    async def apps(self) -> list[App]:
        controller = self._live()
        self._require(controller, Capability.APPS)
        return await controller.apps()

    async def launch(self, app_id: str) -> None:
        controller = self._live()
        self._require(controller, Capability.APPS)
        await controller.launch(app_id)

    async def set_text(self, text: str) -> None:
        """Replace the text in the focused text field on the device."""
        controller = self._live()
        self._require(controller, Capability.TEXT_ENTRY)
        await controller.set_text(text)
