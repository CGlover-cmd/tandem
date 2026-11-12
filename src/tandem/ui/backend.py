"""What the UI needs from the engine.

This is the UI's side of the service API. The engine adapter (and `DemoBackend` until then)
implements `Backend`. The enums mirror the engine's `DeviceKind` and `ConnectionState`
values so the adapter is a straight mapping.

Device names and ids are private (docs/PRIVACY.md). The UI shows names on screen but never
logs them.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
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
PHOTO_BACKGROUND = "photo"
"""The user's own picture, saved by `set_background_photo`."""
BACKGROUNDS = (*NEUTRAL_BACKGROUNDS, *GRADIENT_BACKGROUNDS, PHOTO_BACKGROUND)
"""Window backgrounds the user can pick in Settings. The front end defines their colours."""
DEFAULT_BACKGROUND = "sky"
MAX_PHOTO_BLUR = 24


@dataclass(frozen=True, slots=True)
class Appearance:
    theme: Theme = Theme.SYSTEM
    background: str = DEFAULT_BACKGROUND
    app_icons: bool = True
    """Show real app icons in the launcher, looked up on the App Store (ADR-0012)."""
    onboarded: bool = False
    """The first-run checklist has been closed (it opens by itself until then)."""
    update_check: bool = True
    """Look for a newer Tandem on GitHub when the window opens (Advanced settings)."""
    restore_outputs: bool = False
    """Turn the speakers that were on back on when Tandem starts (Advanced settings)."""
    mute_pc: bool = True
    """Mute the PC's own speakers while AirPlay plays its sound (Advanced settings, ADR-0020)."""
    photo_blur: int = 0
    """Blur over the user's background photo, in pixels."""

    def __post_init__(self) -> None:
        if self.background not in BACKGROUNDS:
            raise ValueError("unknown background")
        if not 0 <= self.photo_blur <= MAX_PHOTO_BLUR:
            raise ValueError("photo blur out of range")


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
    DIRECT = "direct"  # the PC's default output: Windows plays there itself, not Tandem
    MUTED = "muted"  # the PC's default output, muted by Tandem while AirPlay plays (ADR-0020)
    AHEAD = "ahead"  # the PC's default output, kept on while AirPlay plays: it plays ahead


PC_DIRECT = frozenset({OutputState.DIRECT, OutputState.MUTED, OutputState.AHEAD})
"""States of the PC's default output, where Windows plays (Tandem never streams there)."""


class OutputProblem(Enum):
    """Why an output couldn't play; the window words each one with its fix."""

    UNREACHABLE = "unreachable"  # no answer: off, asleep, or on another network
    ACCESS = "access"  # it answered and refused: the Home app's speaker access setting
    FAILED = "failed"  # anything else


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
    problem: OutputProblem | None = None
    """Why it couldn't play, while `state` is FAILED."""


def output_order(output: OutputSnapshot) -> tuple[bool, bool, str, str]:
    """Speakers and TVs first, then the PC: its default output (Windows plays there) first,
    then the rest by name."""
    return (
        output.kind is OutputKind.PC,
        output.state not in PC_DIRECT,
        output.name.casefold(),
        output.id,
    )


class LineUpState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    DONE = "done"
    FAILED = "failed"


class LineUpProblem(Enum):
    TOO_FEW = "tooFew"  # fewer than two speakers playing
    NO_MIC = "noMic"
    NOT_HEARD = "notHeard"  # the beeps weren't heard from one speaker
    NOISY = "noisy"


@dataclass(frozen=True, slots=True)
class LineUpSnapshot:
    """Automatic line-up progress. `output` names the speaker being measured or not heard."""

    state: LineUpState = LineUpState.IDLE
    output: str | None = None
    problem: LineUpProblem | None = None


class GroupState(Enum):
    OFF = "off"
    ON = "on"  # every member that's around is playing
    PARTLY = "partly"  # some members are playing
    STARTING = "starting"


@dataclass(frozen=True, slots=True)
class GroupSnapshot:
    """A saved set of outputs turned on together. `name` is shown, never logged."""

    id: str
    name: str
    outputs: tuple[str, ...]
    state: GroupState = GroupState.OFF


@dataclass(frozen=True, slots=True)
class AudioSnapshot:
    source: AudioSourceChoice = AudioSourceChoice.SYSTEM
    outputs: tuple[OutputSnapshot, ...] = ()
    pc_outputs_hidden: bool = False
    """The PC's default output is left out because it would echo (system audio as source)."""
    groups: tuple[GroupSnapshot, ...] = ()
    lineup: LineUpSnapshot = field(default_factory=LineUpSnapshot)


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


# --- Cast the screen to an Apple TV (Phase 8, ADR-0006 addendum) ---------------------------


class CastQuality(Enum):
    LOW = "low"  # 720p: for a busy Wi-Fi network
    STANDARD = "standard"  # 1080p
    HIGH = "high"  # 1080p at a higher bit rate: sharper text and motion


@dataclass(frozen=True, slots=True)
class ScreenInfo:
    """One of the PC's displays: its place and size only (a monitor's name can identify it)."""

    index: int
    width: int
    height: int
    primary: bool = False


class CastState(Enum):
    STARTING = "starting"
    PLAYING = "playing"
    ENDED = "ended"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CastSnapshot:
    """The screen cast: one at a time, to one TV."""

    device_id: str
    state: CastState
    problem: str | None = None
    """A `Problem` code while `state` is FAILED."""


@dataclass(frozen=True, slots=True)
class CastChanged:
    cast: CastSnapshot | None


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


@dataclass(frozen=True, slots=True)
class HomeSnapshot:
    """Tandem in the Home app (ADR-0016). Switch names are Tandem's own, not personal."""

    enabled: bool = False
    running: bool = False
    paired: bool = False
    setup_code: str | None = None
    """Shown in Settings until the Home app has added Tandem."""
    failed: bool = False
    switches: tuple[tuple[str, str, bool], ...] = ()


@dataclass(frozen=True, slots=True)
class HomeUpdated:
    home: HomeSnapshot


BackendEvent = (
    HomeUpdated
    | DeviceUpdated
    | DeviceRemoved
    | DiscoveryChanged
    | AppearanceChanged
    | ControlsChanged
    | AudioChanged
    | SendChanged
    | CastChanged
    | MusicChanged
)
Listener = Callable[[BackendEvent], None]
Unsubscribe = Callable[[], None]


class Problem:
    """What went wrong, as a code. The window holds the words (`problemText` in strings.ts)."""

    NOT_AVAILABLE = "notAvailable"
    PAIR_FIRST = "pairFirst"
    NO_PAIRING_NEEDED = "noPairingNeeded"
    PIN_EXPIRED = "pinExpired"
    COULD_NOT_PAIR = "couldNotPair"
    WRONG_PIN = "wrongPin"
    NOT_CONNECTED = "notConnected"
    CANT_DO_THAT = "cantDoThat"
    NO_RESPONSE = "noResponse"
    NO_TEXT_FIELD = "noTextField"
    NOTHING_PLAYING = "nothingPlaying"
    APP_CANT = "appCant"
    APP_DIDNT_RESPOND = "appDidntRespond"
    SPEAKER_GONE = "speakerGone"
    NO_AUDIO = "noAudio"
    NO_SEND = "noSend"
    NOT_A_TV = "notATv"
    FILE_GONE = "fileGone"
    CONNECT_FIRST = "connectFirst"
    NO_LOCATION = "noLocation"
    HOME_UNAVAILABLE = "homeUnavailable"
    HOME_FAILED = "homeFailed"
    BAD_GROUP = "badGroup"
    GROUP_NONE_PLAYED = "groupNonePlayed"
    GROUP_GONE = "groupGone"
    NO_SCREEN = "noScreen"
    CAST_FAILED = "castFailed"
    CAST_REFUSED = "castRefused"


class BackendError(Exception):
    """A command didn't work. `code` is a `Problem` value; the window turns it into words.

    `str(error)` is the code, so it holds no private data and is safe to log.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class HomeError(BackendError):
    """The Home bridge couldn't be turned on."""


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

    # Casting the screen

    async def screens(self) -> list[ScreenInfo]:
        """The PC's displays that can be cast, the main one first; empty if it can't cast."""
        ...

    def cast(self) -> CastSnapshot | None:
        """The screen cast, while it starts or plays, or how the last one ended."""
        ...

    async def cast_screen(
        self, device_id: str, screen: int, quality: CastQuality, sound: bool
    ) -> None:
        """Show a screen of this PC (and its sound) on an Apple TV, a few seconds behind.
        Replaces any other cast. Problems show in `cast()`, never raised."""
        ...

    async def stop_cast(self) -> None: ...

    # Tandem in the Home app

    def home(self) -> HomeSnapshot: ...

    async def set_home_bridge(self, on: bool) -> None:
        """Turn the Home bridge on or off; the choice is saved."""
        ...

    async def line_up(self) -> None:
        """Measure each playing speaker's lag with the microphone and set the delays so they
        all play together. Progress shows in `AudioSnapshot.lineup`."""
        ...

    # Speaker groups

    async def save_group(self, name: str, outputs: Sequence[str]) -> None:
        """Save outputs as a named group (a group with the same name is replaced)."""
        ...

    async def delete_group(self, group_id: str) -> None: ...

    async def set_group(self, group_id: str, on: bool) -> None:
        """Turn every member on or off. Raises AudioError only if none would play."""
        ...

    # Housekeeping

    async def set_window_visible(self, visible: bool) -> None:
        """The window was shown or hidden: scan less often while hidden and nothing plays."""
        ...

    async def write_diagnostics(self) -> Path | None:
        """Write a redacted diagnostics zip for a bug report; None if there's nothing to write."""
        ...
