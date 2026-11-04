"""What the UI needs from the engine.

This is the UI's side of the service API. The engine adapter (and `DemoBackend` until then)
implements `Backend`. The enums mirror the engine's `DeviceKind` and `ConnectionState`
values so the adapter is a straight mapping.

Device names and ids are private (docs/PRIVACY.md). The UI shows names on screen but never
logs them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
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
    app_icons: bool = True
    """Show real app icons in the launcher, looked up on the App Store (ADR-0012)."""

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


# --- Typed commands (Phase 10a) -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """What a typed command did, or would do. Holds device names: show it, never log it."""

    status: str
    """ready (preview only), done, help, needsInfo, notUnderstood, notAvailable or failed."""
    code: str
    """What it is about, e.g. "pause" or "whichDevice"; the front end holds the words."""
    params: dict[str, str] = field(default_factory=dict[str, str])
    suggestions: tuple[str, ...] = ()
    """Whole commands to offer instead, or examples."""


class CommandRunner(Protocol):
    def preview_command(self, text: str) -> CommandOutcome:
        """What running `text` would do. Touches no device, so it can run on every keystroke."""
        ...

    async def run_command(self, text: str) -> CommandOutcome: ...


# --- Audio outputs (Phases 4 and 5) and sending media (Phase 7) -------------------------


class OutputKind(Enum):
    AIRPLAY = "airplay"  # an AirPlay device, by its device id
    PC = "pc"  # one of the PC's own sound outputs


class OutputState(Enum):
    OFF = "off"
    STARTING = "starting"
    STREAMING = "streaming"
    WAITING = "waiting"  # the connection dropped; it resumes on reconnect
    FAILED = "failed"


class AudioSourceChoice(Enum):
    SYSTEM = "system"  # whatever the PC plays
    PLAYER = "player"  # Tandem's own player (files and radio)


MAX_DELAY_MS = 10_000


@dataclass(frozen=True, slots=True)
class OutputSnapshot:
    """One place the sound can go. `name` is shown on screen, never logged."""

    id: str
    name: str
    kind: OutputKind
    state: OutputState = OutputState.OFF
    volume: float | None = None
    """0 to 100; None until the user sets it (the device keeps its own volume)."""
    delay_ms: int = 0
    """Extra delay for this output, to line it up with the others by ear."""
    device_kind: DeviceKind | None = None
    needs_pairing: bool = False


@dataclass(frozen=True, slots=True)
class AudioSnapshot:
    source: AudioSourceChoice = AudioSourceChoice.SYSTEM
    outputs: tuple[OutputSnapshot, ...] = ()
    pc_outputs_hidden: bool = False
    """The PC's default output is left out because it would echo (system audio as source)."""


@dataclass(frozen=True, slots=True)
class AudioChanged:
    audio: AudioSnapshot


class SendState(Enum):
    STARTING = "starting"
    PLAYING = "playing"
    ENDED = "ended"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SendSnapshot:
    """What was last sent to a device. `title` is a file name or link host: never logged."""

    state: SendState
    title: str | None = None


@dataclass(frozen=True, slots=True)
class SendChanged:
    device_id: str
    send: SendSnapshot | None


# --- What the PC is playing (Phase 6) -------------------------------------------------------


class MusicCommand(Enum):
    PLAY_PAUSE = "play_pause"
    NEXT = "next"
    PREVIOUS = "previous"


@dataclass(frozen=True, slots=True)
class MusicSnapshot:
    """What an app on this PC is playing (Spotify, Apple Music, a browser...). Titles are
    personal: shown on screen only, never logged."""

    app: str | None
    """The app's name, e.g. "Apple Music"."""
    state: str = "other"  # playing, paused, stopped, other
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    position: float | None = None
    """Seconds into the item at `position_at`; None for live streams."""
    duration: float | None = None
    position_at: float = 0.0
    """`time.monotonic()` when `position` was read; count on from here while playing."""
    commands: frozenset[MusicCommand] = frozenset[MusicCommand]()
    """What the app allows right now."""
    can_seek: bool = False
    artwork: int | None = None
    """Changes whenever the artwork does; None when there is none."""


@dataclass(frozen=True, slots=True)
class MusicArtwork:
    """Artwork for what's playing. Kept in memory and sent to the window only."""

    data: bytes
    mimetype: str


@dataclass(frozen=True, slots=True)
class MusicChanged:
    music: MusicSnapshot | None
    """None when no app on the PC is playing media."""


BackendEvent = (
    DeviceUpdated
    | DeviceRemoved
    | DiscoveryChanged
    | AppearanceChanged
    | ControlsChanged
    | AudioChanged
    | SendChanged
    | MusicChanged
)
Listener = Callable[[BackendEvent], None]
Unsubscribe = Callable[[], None]


class BackendError(Exception):
    """A command didn't work. `str(error)` is safe to show the user; it holds no private data."""


class MediaError(BackendError):
    """Sending media didn't work."""


class AudioError(BackendError):
    """An output couldn't be turned on or changed."""


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

    def music(self) -> MusicSnapshot | None:
        """What an app on the PC is playing now; changes arrive as `MusicChanged`."""
        ...

    def music_artwork(self) -> MusicArtwork | None: ...

    async def music_command(self, command: MusicCommand) -> None:
        """Play/pause, next or previous in the app that's playing. Raises `ControlError` if
        the app doesn't allow it or doesn't respond."""
        ...

    async def music_seek(self, position: float) -> None:
        """Move to `position` seconds in the app that's playing. Raises `ControlError`."""
        ...

    def preview_command(self, text: str) -> CommandOutcome:
        """What running the typed command `text` would do, without running it."""
        ...

    async def run_command(self, text: str) -> CommandOutcome:
        """Run a typed command ("pause", "volume 30 on loft"). Problems are outcomes, not
        errors."""
        ...

    # Audio outputs and sending media

    def audio(self) -> AudioSnapshot: ...

    async def set_output(self, output_id: str, on: bool) -> None:
        """Turn an output on (connecting an AirPlay device if needed) or off. Raises
        `AudioError`."""
        ...

    async def set_output_volume(self, output_id: str, level: float) -> None: ...

    async def set_output_delay(self, output_id: str, delay_ms: int) -> None: ...

    async def set_audio_source(self, source: AudioSourceChoice) -> None: ...

    def send(self, device_id: str) -> SendSnapshot | None:
        """What was last sent to the device, while it's playing or just after."""
        ...

    async def send_media(self, device_id: str, location: str) -> None:
        """Play a link or a file on this PC on an Apple TV. Raises `MediaError`. The location
        is personal: never log it."""
        ...

    async def stop_media(self, device_id: str) -> None: ...
