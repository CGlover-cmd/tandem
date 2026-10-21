"""What the UI needs from the engine.

This is the UI's side of the service API. The engine adapter (and `DemoBackend` until then)
implements `Backend`. The enums mirror the engine's `DeviceKind` and `ConnectionState`
values so the adapter is a straight mapping.

Device names and ids are private (docs/PRIVACY.md). The UI shows names on screen but never
logs them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class DeviceKind(Enum):
    APPLE_TV = "apple_tv"
    HOMEPOD = "homepod"
    RECEIVER = "receiver"  # third-party AirPlay 2 speaker, soundbar or TV
    OTHER = "other"


class LinkState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    WAITING = "waiting"  # waiting to retry after a failed attempt or a dropped connection
    FAILED = "failed"  # gave up retrying


@dataclass(frozen=True, slots=True)
class DeviceSnapshot:
    """Everything the UI shows about one device, at one moment."""

    id: str
    name: str
    kind: DeviceKind
    state: LinkState = LinkState.DISCONNECTED
    needs_pairing: bool = False
    """The device must be paired (PIN) before it can connect."""
    retry_in: float | None = None
    """Seconds until the next attempt, when `state` is WAITING."""


class Theme(Enum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


NEUTRAL_BACKGROUNDS = ("mist", "sand", "slate")
GRADIENT_BACKGROUNDS = ("sky", "dusk", "meadow", "sunrise", "aurora")
BACKGROUNDS = NEUTRAL_BACKGROUNDS + GRADIENT_BACKGROUNDS
"""Window backgrounds the user can pick in Settings. The front end defines their colours."""


@dataclass(frozen=True, slots=True)
class Appearance:
    theme: Theme = Theme.SYSTEM
    background: str = "mist"

    def __post_init__(self) -> None:
        if self.background not in BACKGROUNDS:
            raise ValueError("unknown background")


@dataclass(frozen=True, slots=True)
class DeviceUpdated:
    device: DeviceSnapshot


@dataclass(frozen=True, slots=True)
class DeviceRemoved:
    device_id: str


@dataclass(frozen=True, slots=True)
class DiscoveryChanged:
    active: bool


@dataclass(frozen=True, slots=True)
class AppearanceChanged:
    appearance: Appearance


# --- Remote and media controls (Phase 3) -------------------------------------------------


class RemoteKey(Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    SELECT = "select"
    MENU = "menu"  # "back" on the Siri Remote
    HOME = "home"
    PLAY_PAUSE = "play_pause"
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"


class KeyAction(Enum):
    TAP = "tap"
    DOUBLE_TAP = "double_tap"
    HOLD = "hold"


class MediaCommand(Enum):
    PLAY_PAUSE = "play_pause"
    NEXT = "next"
    PREVIOUS = "previous"
    SKIP_FORWARD = "skip_forward"
    SKIP_BACKWARD = "skip_backward"


class Volume(Enum):
    LEVEL = "level"  # a slider, 0 to 100
    STEPS = "steps"  # up and down buttons only
    NONE = "none"  # use the TV's own remote


@dataclass(frozen=True, slots=True)
class NowPlayingSnapshot:
    """What's playing. Shown on screen only: titles are personal, so never log them."""

    state: str = "idle"  # idle, loading, paused, playing, stopped, seeking, unknown
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    series: str | None = None
    app: str | None = None
    position: float | None = None
    total_time: float | None = None


@dataclass(frozen=True, slots=True)
class ControlsSnapshot:
    """What a connected device's controls can do right now."""

    remote: bool = False
    """Arrow keys, select, back and home."""
    media: frozenset[MediaCommand] = frozenset[MediaCommand]()
    volume: Volume = Volume.NONE
    volume_level: float | None = None
    power: str = "unknown"  # on, off, unknown
    can_power: bool = False
    now_playing: NowPlayingSnapshot | None = None
    """None when the device doesn't report what's playing."""
    apps: bool = False
    """The device can list its apps and open one."""
    text_entry: bool = False
    """The device accepts typed text into its focused text field."""
    keyboard: bool = False
    """The device is showing an on-screen keyboard and waiting for text right now."""


@dataclass(frozen=True, slots=True)
class AppInfo:
    """An app on the device that can be opened. Shown on screen only; never logged."""

    id: str
    name: str


MAX_TEXT = 500
"""The longest text the window sends to a device's text field."""


@dataclass(frozen=True, slots=True)
class ControlsChanged:
    device_id: str
    controls: ControlsSnapshot | None
    """None once the device disconnects."""


BackendEvent = (
    DeviceUpdated | DeviceRemoved | DiscoveryChanged | AppearanceChanged | ControlsChanged
)
Listener = Callable[[BackendEvent], None]
Unsubscribe = Callable[[], None]


class BackendError(Exception):
    """A command didn't work. `str(error)` is safe to show the user; it holds no private data."""


class PairingError(BackendError):
    """Pairing did not succeed."""


class ControlError(BackendError):
    """A remote, media, volume or power command didn't work."""


class WrongPinError(PairingError):
    """The PIN did not match; the user may try again."""


class PairingFlow(Protocol):
    """One pairing attempt. The device shows a PIN; the user types it into Tandem.

    Some devices ask for more than one: an Apple TV pairs remote control and AirPlay
    separately, and shows a new PIN for each.
    """

    @property
    def steps(self) -> int:
        """How many PINs the user will enter in all (at least 1)."""
        ...

    async def submit_pin(self, pin: str) -> bool:
        """Check the PIN the device is showing now.

        Returns True if the device now shows the next PIN, False when pairing is complete.
        Raises `WrongPinError` (the device shows a fresh PIN to retry) or `PairingError`.
        """
        ...

    async def cancel(self) -> None: ...


class Backend(Protocol):
    def subscribe(self, listener: Listener) -> Unsubscribe:
        """Call `listener` on the asyncio loop thread for every change."""
        ...

    def devices(self) -> list[DeviceSnapshot]: ...

    async def start(self) -> None:
        """Start discovery. Devices arrive through `subscribe`."""
        ...

    async def stop(self) -> None: ...

    async def connect(self, device_id: str) -> None: ...

    async def disconnect(self, device_id: str) -> None: ...

    async def begin_pairing(self, device_id: str) -> PairingFlow:
        """Ask the device to show a PIN. Raises `PairingError` if it can't."""
        ...

    def appearance(self) -> Appearance: ...

    def controls(self, device_id: str) -> ControlsSnapshot | None:
        """The device's controls while it is connected and ready, else None."""
        ...

    async def press(self, device_id: str, key: RemoteKey, action: KeyAction) -> None:
        """Press a remote key. Raises `ControlError`."""
        ...

    async def media(self, device_id: str, command: MediaCommand) -> None: ...

    async def set_volume(self, device_id: str, level: float) -> None:
        """Set the volume, 0 to 100, on a device whose `volume` is LEVEL."""
        ...

    async def set_power(self, device_id: str, on: bool) -> None: ...

    async def apps(self, device_id: str) -> list[AppInfo]:
        """The apps the device can open, on a device whose `apps` is True."""
        ...

    async def launch_app(self, device_id: str, app_id: str) -> None: ...

    async def set_text(self, device_id: str, text: str) -> None:
        """Replace the text in the device's focused text field. The text is personal (it may
        be a search or a password): never log it."""
        ...

    async def set_appearance(self, appearance: Appearance) -> None:
        """Save the user's choice and publish `AppearanceChanged`."""
        ...
