"""Invented devices behind the engine's device seam (review A2, ADR-0019).

`DemoDevices` implements the engine's `Backend` with made-up receivers, so `--demo` runs the
real engine and bridge: the same pairing flow, connection retries, controls, outputs and typed
commands as with real devices. The window's tests use it too. Everything here is invented
(docs/PRIVACY.md): names, ids, addresses (192.0.2.x), apps and tracks.

Behaviour worth seeing in the window:
- the TV needs pairing first, with two PINs like a real Apple TV (remote control, then
  AirPlay); any 4 digits work except 0000, which the TV "rejects";
- the soundbar's first connection attempt fails, so the retry state shows;
- the TV lists apps, and opening Search brings up its on-screen keyboard (Back closes it);
- an invented music app on the PC plays invented tracks, with drawn artwork;
- "Line up automatically" hears each speaker at a made-up lag.
"""

from __future__ import annotations

import array
import asyncio
import dataclasses
import itertools
import math
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from tandem.engine import lineup
from tandem.engine.adapters.demo_music import DemoMusic
from tandem.engine.audio import PcmBuffer
from tandem.engine.audio_hub import LOCAL_PREFIX
from tandem.engine.control import (
    App,
    Artwork,
    Capability,
    ControlUpdate,
    KeyAction,
    KeyboardFocus,
    MediaCommand,
    MediaType,
    NowPlaying,
    PlayState,
    PowerState,
    RemoteKey,
    VolumeControl,
)
from tandem.engine.home_bridge import SwitchSpec
from tandem.engine.models import Device, DeviceKind, LocalOutput, Service
from tandem.engine.pc_media import ChangeKind, PcArtwork, PcMediaCommand, PcNowPlaying
from tandem.engine.player import Track

Sleep = Callable[[float], Awaitable[None]]

WRONG_PIN = "0000"
DEMO_SETUP_CODE = "123-45-678"

TV = "demo-tv"
PATIO = "demo-speaker-1"
OFFICE = "demo-speaker-2"
SOUNDBAR = "demo-soundbar"
FLAKY = SOUNDBAR

_AIRPLAY = frozenset({Service.AIRPLAY, Service.RAOP})
DEMO_DEVICES = (
    Device(
        TV,
        "Living Room TV",
        "192.0.2.21",
        DeviceKind.APPLE_TV,
        "Apple TV 4K",
        frozenset({Service.COMPANION, Service.AIRPLAY, Service.RAOP, Service.MRP}),
        needs_pairing=frozenset({Service.COMPANION, Service.AIRPLAY}),
    ),
    Device(PATIO, "Patio Speaker", "192.0.2.22", DeviceKind.HOMEPOD, "HomePod mini", _AIRPLAY),
    Device(OFFICE, "Office Speaker", "192.0.2.23", DeviceKind.HOMEPOD, "HomePod mini", _AIRPLAY),
    Device(SOUNDBAR, "Den Soundbar", "192.0.2.24", DeviceKind.RECEIVER, "Soundbar", _AIRPLAY),
)

HIDDEN = "demo-speaker-3"
DEMO_HIDDEN = Device(
    HIDDEN,
    "Workshop Speaker",
    "192.0.2.60",
    DeviceKind.RECEIVER,
    "Speaker",
    _AIRPLAY,
    password_required=True,
)
"""Only found by address (192.0.2.60), and it wants a password (any but "wrong")."""
WRONG_PASSWORD = "wrong"


class AuthenticationError(Exception):
    """Named like pyatv's, so the engine reads it as a refusal."""


PC_SPEAKERS = f"{LOCAL_PREFIX}demo-speakers"
PC_HEADPHONES = f"{LOCAL_PREFIX}demo-headphones"
DEMO_PC_OUTPUTS = (
    LocalOutput(PC_SPEAKERS, "Speakers", default=True),
    LocalOutput(PC_HEADPHONES, "Headphones"),
)

# Invented app list for the demo TV; out of order, as a device sends it.
DEMO_APPS = (
    App("com.example.tv", "TV"),
    App("com.example.music", "Music"),
    App("com.example.photos", "Photos"),
    App("com.apple.TVSearch", "Search"),  # built into tvOS: the window draws these icons
    App("com.apple.TVSettings", "Settings"),
    App("com.example.podcasts", "Podcasts"),
    App("com.example.nature", "Nature Hour"),
    App("com.example.arcade", "Arcade Classics"),
    App("com.example.fitness", "Fitness"),
    App("com.example.weather", "Weather Now"),
)
SEARCH_APP = "com.apple.TVSearch"

_TV_CAPS = frozenset(
    {
        Capability.REMOTE,
        Capability.PLAY_PAUSE,
        Capability.NEXT,
        Capability.PREVIOUS,
        Capability.SKIP_FORWARD,
        Capability.SKIP_BACKWARD,
        Capability.NOW_PLAYING,
        Capability.POWER,
        Capability.APPS,
        Capability.TEXT_ENTRY,
    }
)
_SPEAKER_CAPS = frozenset(
    {Capability.PLAY_PAUSE, Capability.NEXT, Capability.PREVIOUS, Capability.NOW_PLAYING}
)


@dataclass(slots=True)
class _DeviceState:
    """What each invented device is doing; kept across reconnects, as a real one would."""

    capabilities: frozenset[Capability]
    volume_control: VolumeControl
    volume: float | None
    power: PowerState = PowerState.ON
    playing: NowPlaying = field(default_factory=NowPlaying)
    keyboard: bool = False


def _initial_state(device_id: str) -> _DeviceState:
    if device_id == TV:
        return _DeviceState(
            _TV_CAPS,
            VolumeControl.STEPS,
            None,
            playing=NowPlaying(
                state=PlayState.PLAYING,
                media_type=MediaType.TV,
                title="A Walk in the Woods",
                series="Nature Hour",
                app_name="TV",
                position=754.0,
                total_time=2640.0,
            ),
        )
    if device_id == SOUNDBAR:
        return _DeviceState(frozenset(), VolumeControl.LEVEL, 25.0)
    return _DeviceState(
        _SPEAKER_CAPS,
        VolumeControl.LEVEL,
        40.0,
        playing=NowPlaying(
            state=PlayState.PAUSED,
            media_type=MediaType.MUSIC,
            title="Morning Light",
            artist="The Example Band",
            album="Daybreak",
            app_name="Music",
            position=61.0,
            total_time=214.0,
        ),
    )


class DemoDevices:
    """The engine's `Backend` (`tandem.engine.service.Backend`) with invented devices.

    `sleep` and `delay` set how long the invented devices take to answer; tests pass a sleep
    that returns at once. The lists below record what the window asked for, for tests.
    """

    def __init__(
        self,
        *,
        sleep: Sleep = asyncio.sleep,
        delay: float = 0.6,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sleep = sleep
        self._delay = delay
        self.devices = list(DEMO_DEVICES)
        self._credentials: set[tuple[str, Service]] = set()
        self._passwords: dict[str, str] = {}
        self._flaky = {FLAKY}
        self._states: dict[str, _DeviceState] = {}
        self.sessions = DemoSessions(clock)
        self.music = DemoMusic()
        self.presses: list[tuple[str, RemoteKey, KeyAction]] = []
        self.launched: list[tuple[str, str]] = []
        self.texts: list[tuple[str, str]] = []
        self.sent: list[tuple[str, str]] = []
        self._lags = itertools.cycle((180, 320, 90, 240))
        self.speakers = DemoSpeakerMute()

    # Storage and discovery

    async def load(self) -> None:
        return None

    async def save(self) -> None:
        return None

    async def scan(self, timeout: float) -> Sequence[Device]:
        return [self._described(d) for d in self.devices]

    async def scan_hosts(self, hosts: Sequence[str], timeout: float) -> Sequence[Device]:
        await self._sleep(self._delay)
        every = [*self.devices, DEMO_HIDDEN]
        return [self._described(d) for d in every if d.address in hosts]

    async def set_password(self, device_id: str, password: str) -> None:
        self._passwords[device_id] = password

    async def describe(self, device_id: str) -> Device | None:
        device = next((d for d in self.devices if d.id == device_id), None)
        return None if device is None else self._described(device)

    def _described(self, device: Device) -> Device:
        paired = frozenset(s for i, s in self._credentials if i == device.id)
        return dataclasses.replace(
            device,
            paired=paired,
            needs_pairing=device.needs_pairing - paired,
            password_set=device.id in self._passwords,
        )

    async def forget(self, device_id: str) -> bool:
        before = len(self._credentials)
        self._credentials = {c for c in self._credentials if c[0] != device_id}
        return len(self._credentials) != before

    # Pairing and connecting

    def pairing(self, device_id: str, service: Service) -> Callable[[], Awaitable[_DemoPairing]]:
        async def start() -> _DemoPairing:
            return _DemoPairing(self, device_id, service)

        return start

    def connector(self, device_id: str) -> Callable[..., Awaitable[_DemoLink]]:
        async def connect(on_lost: Callable[[BaseException | None], None]) -> _DemoLink:
            await self._sleep(self._delay)
            if device_id == HIDDEN and self._passwords.get(device_id, WRONG_PASSWORD) == (
                WRONG_PASSWORD
            ):
                raise AuthenticationError  # the speaker refuses: no password, or the wrong one
            if device_id in self._flaky:
                self._flaky.discard(device_id)
                raise ConnectionRefusedError  # once, so the window shows a retry
            return _DemoLink(device_id)

        return connect

    # Controls

    def controller(self, link: Any) -> DemoController | None:
        if not isinstance(link, _DemoLink):
            return None
        state = self._states.setdefault(link.device_id, _initial_state(link.device_id))
        return DemoController(self, link.device_id, state)

    # Audio

    def audio_sink(self, link: Any) -> DemoSink | None:
        return DemoSink(self._sleep) if isinstance(link, _DemoLink) else None

    def capture(self) -> _DemoCapture:
        return _DemoCapture()  # nothing plays: the audio pipeline fills silence itself

    def local_outputs(self) -> Sequence[LocalOutput]:
        return list(DEMO_PC_OUTPUTS)

    def local_sink(self, output_id: str) -> DemoSink | None:
        known = {o.id for o in DEMO_PC_OUTPUTS}
        return DemoSink(self._sleep) if output_id in known else None

    def microphone(self) -> _DemoMicrophone:
        return _DemoMicrophone(next(self._lags))

    def speaker_mute(self) -> DemoSpeakerMute:
        return self.speakers

    # Media

    def media_sender(self, link: Any) -> _DemoSender | None:
        if not isinstance(link, _DemoLink) or link.device_id != TV:
            return None
        return _DemoSender(self, link.device_id)

    def open_track(self, track: Track) -> Any:
        return self.music.open_track(track)

    def media_sessions(self) -> DemoSessions:
        return self.sessions

    # For tests

    def remove(self, device_id: str) -> None:
        """The device leaves the network (the next scan won't find it)."""
        self.devices = [d for d in self.devices if d.id != device_id]


class _DemoLink:
    def __init__(self, device_id: str) -> None:
        self.device_id = device_id

    async def close(self) -> None:
        return None


class _DemoPairing:
    def __init__(self, demo: DemoDevices, device_id: str, service: Service) -> None:
        self._demo = demo
        self._device_id = device_id
        self._service = service
        self._pin = ""
        self._paired = False

    @property
    def device_provides_pin(self) -> bool:
        return True

    @property
    def has_paired(self) -> bool:
        return self._paired

    async def begin(self) -> None:
        await self._demo._sleep(self._demo._delay)  # pyright: ignore[reportPrivateUsage]

    def pin(self, pin: str) -> None:
        self._pin = pin

    async def finish(self) -> None:
        await self._demo._sleep(self._demo._delay)  # pyright: ignore[reportPrivateUsage]
        if self._pin != WRONG_PIN:
            self._paired = True
            self._demo._credentials.add((self._device_id, self._service))  # pyright: ignore[reportPrivateUsage]

    async def close(self) -> None:
        return None


class DemoController:
    """Controls on one invented device. Changes are pushed back, as a real device would."""

    def __init__(self, demo: DemoDevices, device_id: str, state: _DeviceState) -> None:
        self._demo = demo
        self._device_id = device_id
        self._state = state
        self._on_update: Callable[[ControlUpdate], None] | None = None

    def capabilities(self) -> frozenset[Capability]:
        return self._state.capabilities

    def volume_control(self) -> VolumeControl:
        return self._state.volume_control

    def volume(self) -> float | None:
        return self._state.volume

    def power(self) -> PowerState:
        return self._state.power

    def keyboard_focused(self) -> bool:
        return self._state.keyboard

    async def press(self, key: RemoteKey, action: KeyAction) -> None:
        self._demo.presses.append((self._device_id, key, action))
        if key is RemoteKey.PLAY_PAUSE:
            self._toggle()
        elif key in (RemoteKey.MENU, RemoteKey.HOME) and self._state.keyboard:
            self._state.keyboard = False
            self._push(KeyboardFocus(False))

    async def media(self, command: MediaCommand) -> None:
        if command is MediaCommand.PLAY_PAUSE:
            self._toggle()
        elif command in (MediaCommand.PLAY, MediaCommand.PAUSE):
            self._set_playing(command is MediaCommand.PLAY)

    async def seek(self, position: float) -> None:
        self._state.playing = dataclasses.replace(self._state.playing, position=position)
        self._push(self._state.playing)

    async def set_volume(self, level: float) -> None:
        self._state.volume = max(0.0, min(100.0, level))
        self._push(self._state.volume)

    async def volume_step(self, up: bool) -> None:
        key = RemoteKey.VOLUME_UP if up else RemoteKey.VOLUME_DOWN
        self._demo.presses.append((self._device_id, key, KeyAction.TAP))
        if self._state.volume is not None:
            await self.set_volume(self._state.volume + (10 if up else -10))

    async def set_power(self, on: bool) -> None:
        self._state.power = PowerState.ON if on else PowerState.OFF
        self._push(self._state.power)

    async def now_playing(self) -> NowPlaying:
        return self._state.playing

    async def artwork(self, width: int | None, height: int | None) -> Artwork | None:
        return None

    async def apps(self) -> list[App]:
        await self._demo._sleep(self._demo._delay / 2)  # pyright: ignore[reportPrivateUsage]
        return list(DEMO_APPS)

    async def launch(self, app_id: str) -> None:
        app = next((a for a in DEMO_APPS if a.id == app_id), None)
        if app is None:
            raise ValueError("no such app")
        self._demo.launched.append((self._device_id, app_id))
        self._state.playing = dataclasses.replace(self._state.playing, app_name=app.name)
        self._push(self._state.playing)
        focused = app_id == SEARCH_APP
        if focused != self._state.keyboard:
            self._state.keyboard = focused
            self._push(KeyboardFocus(focused))

    async def set_text(self, text: str) -> None:
        self._demo.texts.append((self._device_id, text))

    def start(self, on_update: Callable[[ControlUpdate], None]) -> None:
        self._on_update = on_update

    def stop(self) -> None:
        self._on_update = None

    def _toggle(self) -> None:
        self._set_playing(self._state.playing.state is not PlayState.PLAYING)

    def _set_playing(self, playing: bool) -> None:
        state = PlayState.PLAYING if playing else PlayState.PAUSED
        self._state.playing = dataclasses.replace(self._state.playing, state=state)
        self._push(self._state.playing)

    def _push(self, update: ControlUpdate) -> None:
        if self._on_update is not None:
            self._on_update(update)


class DemoSink:
    """Takes audio at about real time and drops it."""

    FRAMES = 352

    def __init__(self, sleep: Sleep) -> None:
        self._sleep = sleep
        self.volume: float | None = None

    async def set_volume(self, level: float) -> None:
        self.volume = level

    async def play(self, buffer: PcmBuffer, *, title: str, artist: str) -> None:
        pace = self.FRAMES / 44_100
        while await buffer.read(self.FRAMES):
            await self._sleep(pace)


class _DemoCapture:
    def start(self, on_pcm: Callable[[bytes], None]) -> None:
        return None

    def stop(self) -> None:
        return None


class DemoSpeakerMute:
    """The demo PC's speakers: a mute switch in memory, so the window shows "Muted"."""

    def __init__(self) -> None:
        self.mutes: dict[str, bool] = {}

    def available(self) -> bool:
        return True

    def default_output(self) -> str | None:
        return next((o.id for o in DEMO_PC_OUTPUTS if o.default), None)

    def muted(self, endpoint: str) -> bool:
        return self.mutes.get(endpoint, False)

    def set_muted(self, endpoint: str, on: bool) -> None:
        self.mutes[endpoint] = on


class _DemoMicrophone:
    """'Hears' the line-up beeps `lag_ms` after they were sent."""

    def __init__(self, lag_ms: int) -> None:
        self._lag_ms = lag_ms

    def start(self, on_pcm: Callable[[bytes], None]) -> None:
        on_pcm(_heard_beeps(self._lag_ms))

    def stop(self) -> None:
        return None


def _heard_beeps(lag_ms: int) -> bytes:
    """A mono microphone recording: quiet, then the beep pattern after `lag_ms`."""
    rate = lineup.MIC_RATE
    total_ms = lineup.QUIET_MS + lag_ms + lineup.BEEP_STARTS_MS[-1] + lineup.BEEP_MS + 400
    samples = array.array("h", bytes(total_ms * rate // 1000 * 2))
    for start_ms in lineup.BEEP_STARTS_MS:
        start = (lineup.QUIET_MS + lag_ms + start_ms) * rate // 1000
        for i in range(lineup.BEEP_MS * rate // 1000):
            samples[start + i] = int(12_000 * math.sin(2 * math.pi * lineup.BEEP_HZ * i / rate))
    return samples.tobytes()


class _DemoSender:
    """Plays a video or link 'on the TV' until it is stopped."""

    def __init__(self, demo: DemoDevices, device_id: str) -> None:
        self._demo = demo
        self._device_id = device_id

    async def play_url(self, url: str) -> None:
        self._demo.sent.append((self._device_id, url))
        await asyncio.Event().wait()


# Invented music on the PC: title, artist, album, length, artwork colours.
DEMO_MUSIC_APP = "Demo Player"
DEMO_TRACKS = (
    ("Morning Light", "The Example Band", "Daybreak", 214.0, ("#5B8CFF", "#B36BFF")),
    ("Paper Boats", "The Example Band", "Daybreak", 187.0, ("#FF8A5B", "#FFC85B")),
    ("Night Bus", "Imaginary Orchestra", "City Hours", 242.0, ("#2BB673", "#2B7BB6")),
)


class DemoSessions:
    """Windows' media controls with one invented music app playing invented tracks."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._track = 0
        self._playing = True
        self._position = 42.0
        self._position_at = clock()
        self._open = True
        self._on_change: Callable[[ChangeKind], None] | None = None

    async def watch(self, on_change: Callable[[ChangeKind], None]) -> None:
        self._on_change = on_change

    async def unwatch(self) -> None:
        self._on_change = None

    async def current(self) -> PcNowPlaying | None:
        if not self._open:
            return None
        title, artist, album, length, _colours = DEMO_TRACKS[self._track]
        position = self._now()
        if position >= length:  # the track ended: on to the next, as a player would
            self._next(1)
            return await self.current()
        return PcNowPlaying(
            state="playing" if self._playing else "paused",
            title=title,
            artist=artist,
            album=album,
            app=DEMO_MUSIC_APP,
            can_play_pause=True,
            can_next=True,
            can_previous=True,
            can_seek=True,
            position=position,
            duration=length,
            has_artwork=True,
        )

    async def artwork(self) -> PcArtwork | None:
        if not self._open:
            return None
        return PcArtwork(_artwork(DEMO_TRACKS[self._track][4]), "image/svg+xml")

    async def command(self, command: PcMediaCommand) -> bool:
        if not self._open:
            return False
        if command is PcMediaCommand.PLAY_PAUSE:
            self._position, self._position_at = self._now(), self._clock()
            self._playing = not self._playing
            self._changed(ChangeKind.PLAYBACK)
        else:
            self._next(1 if command is PcMediaCommand.NEXT else -1)
        return True

    async def seek(self, position: float) -> bool:
        if not self._open:
            return False
        length = DEMO_TRACKS[self._track][3]
        self._position, self._position_at = min(max(0.0, position), length), self._clock()
        self._changed(ChangeKind.TIMELINE)
        return True

    def close_app(self) -> None:
        """The demo app closes, as if nothing played on the PC (used by tests)."""
        self._open = False
        self._changed(ChangeKind.SESSION)

    def _next(self, step: int) -> None:
        self._track = (self._track + step) % len(DEMO_TRACKS)
        self._position, self._position_at = 0.0, self._clock()
        self._changed(ChangeKind.MEDIA)

    def _now(self) -> float:
        if not self._playing:
            return self._position
        return self._position + (self._clock() - self._position_at)

    def _changed(self, kind: ChangeKind) -> None:
        if self._on_change is not None:
            self._on_change(kind)


def _artwork(colours: tuple[str, str]) -> bytes:
    """A gradient square with a note on it, standing in for album art."""
    start, end = colours
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{start}"/><stop offset="1" stop-color="{end}"/>'
        '</linearGradient></defs><rect width="120" height="120" fill="url(#g)"/>'
        '<path d="M52 82a10 10 0 1 1-6-9V38l32-7v40a10 10 0 1 1-6-9V44l-20 4z" '
        'fill="white" fill-opacity="0.85"/></svg>'
    ).encode()


class DemoBridgeServer:
    """The Home bridge, pretend: a fixed setup code, nothing advertised on the network."""

    def __init__(self) -> None:
        self.states: dict[str, bool] = {}

    async def start(
        self, switches: Sequence[SwitchSpec], on_set: Callable[[str, bool], None]
    ) -> str:
        return DEMO_SETUP_CODE

    async def stop(self) -> None:
        return None

    def set_state(self, switch_id: str, on: bool) -> None:
        self.states[switch_id] = on

    @property
    def paired(self) -> bool:
        return False
