"""A stand-in backend with invented devices, so the UI can run without the engine or a network.

Behaviour worth seeing in the UI:
- devices appear one at a time, as discovery would find them;
- the TV needs PIN pairing first, with two PINs like a real Apple TV (remote control, then
  AirPlay); any 4 digits work except 0000, which is "wrong";
- the soundbar's first connection attempt fails, so the retry state shows;
- the TV lists apps, and opening Search brings up its on-screen keyboard (Back closes it);
- an invented music app on the PC plays invented tracks, with drawn artwork, for the Music
  tab and the now-playing bar.

Typed commands need the engine's parser, which the UI layer doesn't import, so `tandem.ui.app`
plugs one in (`commands`, from `tandem.bridge.demo_commands`).

The appearance setting is kept in memory, or in a small JSON file when `appearance_file` is
given, so a background picked in Settings survives a restart.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path

from tandem.ui.backend import (
    MAX_TEXT,
    Appearance,
    AppearanceChanged,
    AppInfo,
    BackendEvent,
    CommandOutcome,
    CommandRunner,
    ControlError,
    ControlsChanged,
    ControlsSnapshot,
    DeviceKind,
    DeviceRemoved,
    DeviceSnapshot,
    DeviceUpdated,
    DiscoveryChanged,
    KeyAction,
    LinkState,
    Listener,
    MediaCommand,
    MusicArtwork,
    MusicChanged,
    MusicCommand,
    MusicSnapshot,
    NowPlayingSnapshot,
    PairingError,
    PairingFlow,
    RemoteKey,
    Theme,
    Unsubscribe,
    Volume,
    WrongPinError,
)
from tandem.ui.demo_audio import DemoAudio
from tandem.ui.demo_library import DemoLibrary

_LOGGER = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]

WRONG_PIN = "0000"
TV_PIN_STEPS = 2

# Invented devices only (docs/PRIVACY.md).
DEMO_DEVICES = (
    DeviceSnapshot("demo-tv", "Living Room TV", DeviceKind.APPLE_TV, needs_pairing=True),
    DeviceSnapshot("demo-speaker-1", "Patio Speaker", DeviceKind.HOMEPOD),
    DeviceSnapshot("demo-speaker-2", "Office Speaker", DeviceKind.HOMEPOD),
    DeviceSnapshot("demo-soundbar", "Den Soundbar", DeviceKind.RECEIVER),
)
FLAKY_DEVICE = "demo-soundbar"

NOT_CONNECTED = "This device isn't connected."
CANT_DO_THAT = "This device can't do that right now."

# What each kind of demo device can do once connected (invented media, docs/PRIVACY.md).
_ALL_MEDIA = frozenset(MediaCommand)
DEMO_CONTROLS = {
    DeviceKind.APPLE_TV: ControlsSnapshot(
        remote=True,
        media=_ALL_MEDIA,
        volume=Volume.STEPS,
        power="on",
        can_power=True,
        apps=True,
        text_entry=True,
        now_playing=NowPlayingSnapshot(
            "playing",
            "A Walk in the Woods",
            series="Nature Hour",
            app="TV",
            position=754.0,
            total_time=2640.0,
        ),
    ),
    DeviceKind.HOMEPOD: ControlsSnapshot(
        media=frozenset({MediaCommand.PLAY_PAUSE, MediaCommand.NEXT, MediaCommand.PREVIOUS}),
        volume=Volume.LEVEL,
        volume_level=40.0,
        now_playing=NowPlayingSnapshot(
            "paused",
            "Morning Light",
            artist="The Example Band",
            album="Daybreak",
            app="Music",
            position=61.0,
            total_time=214.0,
        ),
    ),
    DeviceKind.RECEIVER: ControlsSnapshot(volume=Volume.LEVEL, volume_level=25.0),
}


# Invented app list for the demo TV (docs/PRIVACY.md); out of order, as a device sends it.
DEMO_APPS = (
    AppInfo("com.example.tv", "TV"),
    AppInfo("com.example.music", "Music"),
    AppInfo("com.example.photos", "Photos"),
    AppInfo("com.apple.TVSearch", "Search"),  # built into tvOS: the window draws these icons
    AppInfo("com.apple.TVSettings", "Settings"),
    AppInfo("com.example.podcasts", "Podcasts"),
    AppInfo("com.example.nature", "Nature Hour"),
    AppInfo("com.example.arcade", "Arcade Classics"),
    AppInfo("com.example.fitness", "Fitness"),
    AppInfo("com.example.weather", "Weather Now"),
)
SEARCH_APP = "com.apple.TVSearch"

# Invented music on the PC (docs/PRIVACY.md): title, artist, album, length, artwork colours.
DEMO_MUSIC_APP = "Demo Player"
DEMO_TRACKS = (
    ("Morning Light", "The Example Band", "Daybreak", 214.0, ("#5B8CFF", "#B36BFF")),
    ("Paper Boats", "The Example Band", "Daybreak", 187.0, ("#FF8A5B", "#FFC85B")),
    ("Night Bus", "Imaginary Orchestra", "City Hours", 242.0, ("#2BB673", "#2B7BB6")),
)
NOTHING_PLAYING = "Nothing is playing on this PC."


def _demo_artwork(colours: tuple[str, str]) -> bytes:
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


class DemoBackend(DemoAudio, DemoLibrary):
    def __init__(
        self,
        *,
        sleep: Sleep = asyncio.sleep,
        delay: float = 0.6,
        retry_after: float = 2.0,
        appearance_file: Path | None = None,
        commands: CommandRunner | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.commands = commands
        self._clock = clock
        self._track = 0
        self._artwork_id = 1
        self._music: MusicSnapshot | None = self._track_snapshot("playing", 42.0)
        self._sleep = sleep
        self._appearance_file = appearance_file
        self._appearance = _load_appearance(appearance_file)
        self._delay = delay
        self._retry_after = retry_after
        self._devices: dict[str, DeviceSnapshot] = {}
        self._listeners: list[Listener] = []
        self._connecting: dict[str, asyncio.Task[None]] = {}
        self._flaky = {FLAKY_DEVICE}
        self._controls: dict[str, ControlsSnapshot] = {}
        self.presses: list[tuple[str, RemoteKey, KeyAction]] = []
        self.launched: list[tuple[str, str]] = []
        self.texts: list[tuple[str, str]] = []
        self._init_audio()
        self._init_library(clock)

    def subscribe(self, listener: Listener) -> Unsubscribe:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def devices(self) -> list[DeviceSnapshot]:
        return list(self._devices.values())

    async def start(self) -> None:
        self._publish(DiscoveryChanged(active=True))
        for device in DEMO_DEVICES:
            await self._sleep(self._delay / 2)
            self._set(device)
        self._publish(DiscoveryChanged(active=False))

    async def set_window_visible(self, visible: bool) -> None:
        self.window_visible = visible

    async def write_diagnostics(self) -> Path | None:
        return None  # invented devices: nothing worth reporting

    async def stop(self) -> None:
        for task in list(self._connecting.values()):
            task.cancel()
        self._connecting.clear()

    async def connect(self, device_id: str) -> None:
        device = self._get(device_id)
        if device.needs_pairing:
            raise PairingError("Pair this device first.")
        if device_id in self._connecting or device.state is LinkState.CONNECTED:
            return
        task = asyncio.get_running_loop().create_task(self._connect(device_id))
        self._connecting[device_id] = task
        try:
            await asyncio.wait({task})
        finally:
            if self._connecting.get(device_id) is task:
                del self._connecting[device_id]
        if not task.cancelled():
            task.result()

    async def disconnect(self, device_id: str) -> None:
        task = self._connecting.pop(device_id, None)
        if task is not None:
            task.cancel()
        self._update(device_id, state=LinkState.DISCONNECTED, retry_in=None)

    async def begin_pairing(self, device_id: str) -> PairingFlow:
        device = self._get(device_id)
        if not device.needs_pairing:
            raise PairingError("This device doesn't need pairing.")
        await self._sleep(self._delay)
        return _DemoPairing(
            TV_PIN_STEPS, lambda pin, last: self._finish_pairing(device_id, pin, last)
        )

    def appearance(self) -> Appearance:
        return self._appearance

    async def set_appearance(self, appearance: Appearance) -> None:
        self._appearance = appearance
        if self._appearance_file is not None:
            _save_appearance(self._appearance_file, appearance)
        self._publish(AppearanceChanged(appearance))

    # Internals

    async def _connect(self, device_id: str) -> None:
        self._update(device_id, state=LinkState.CONNECTING, retry_in=None)
        await self._sleep(self._delay)
        if device_id in self._flaky:
            self._flaky.discard(device_id)
            self._update(device_id, state=LinkState.WAITING, retry_in=self._retry_after)
            await self._sleep(self._retry_after)
            self._update(device_id, state=LinkState.CONNECTING, retry_in=None)
            await self._sleep(self._delay)
        self._update(device_id, state=LinkState.CONNECTED)

    async def _finish_pairing(self, device_id: str, pin: str, last: bool) -> None:
        await self._sleep(self._delay)
        if pin == WRONG_PIN:
            raise WrongPinError("That PIN didn't match.")
        if last:
            self._update(device_id, needs_pairing=False)

    def _get(self, device_id: str) -> DeviceSnapshot:
        try:
            return self._devices[device_id]
        except KeyError:
            raise PairingError("That device is no longer available.") from None

    def _update(
        self,
        device_id: str,
        *,
        state: LinkState | None = None,
        retry_in: float | None = None,
        needs_pairing: bool | None = None,
    ) -> None:
        device = self._devices.get(device_id)
        if device is None:
            return
        was_connected = device.state is LinkState.CONNECTED
        device = replace(
            device,
            state=device.state if state is None else state,
            retry_in=retry_in,
            needs_pairing=device.needs_pairing if needs_pairing is None else needs_pairing,
        )
        self._set(device)
        connected = device.state is LinkState.CONNECTED
        if connected and not was_connected:
            self._set_controls(device_id, DEMO_CONTROLS.get(device.kind))
        elif was_connected and not connected:
            self._set_controls(device_id, None)

    def _set_controls(self, device_id: str, controls: ControlsSnapshot | None) -> None:
        if controls is None:
            self._controls.pop(device_id, None)
        else:
            self._controls[device_id] = controls
        self._publish(ControlsChanged(device_id, controls))

    def _live(self, device_id: str) -> ControlsSnapshot:
        controls = self._controls.get(device_id)
        if controls is None:
            raise ControlError(NOT_CONNECTED)
        return controls

    def _toggle_playback(self, device_id: str, controls: ControlsSnapshot) -> None:
        playing = controls.now_playing
        if playing is None:
            raise ControlError(CANT_DO_THAT)
        state = "paused" if playing.state == "playing" else "playing"
        self._set_controls(device_id, replace(controls, now_playing=replace(playing, state=state)))

    def _set(self, device: DeviceSnapshot) -> None:
        self._devices[device.id] = device
        self._publish(DeviceUpdated(device))

    # Controls

    def controls(self, device_id: str) -> ControlsSnapshot | None:
        return self._controls.get(device_id)

    async def press(self, device_id: str, key: RemoteKey, action: KeyAction) -> None:
        controls = self._live(device_id)
        if key is RemoteKey.PLAY_PAUSE:
            self._toggle_playback(device_id, controls)
        elif key in (RemoteKey.VOLUME_UP, RemoteKey.VOLUME_DOWN):
            if controls.volume is Volume.NONE:
                raise ControlError(CANT_DO_THAT)
        elif not controls.remote:
            raise ControlError(CANT_DO_THAT)
        elif key in (RemoteKey.MENU, RemoteKey.HOME) and controls.keyboard:
            self._set_controls(device_id, replace(controls, keyboard=False))
        self.presses.append((device_id, key, action))

    async def media(self, device_id: str, command: MediaCommand) -> None:
        controls = self._live(device_id)
        if command not in controls.media:
            raise ControlError(CANT_DO_THAT)
        if command is MediaCommand.PLAY_PAUSE:
            self._toggle_playback(device_id, controls)

    async def set_volume(self, device_id: str, level: float) -> None:
        controls = self._live(device_id)
        if controls.volume is not Volume.LEVEL:
            raise ControlError(CANT_DO_THAT)
        level = min(100.0, max(0.0, level))
        self._set_controls(device_id, replace(controls, volume_level=level))

    async def set_power(self, device_id: str, on: bool) -> None:
        controls = self._live(device_id)
        if not controls.can_power:
            raise ControlError(CANT_DO_THAT)
        self._set_controls(device_id, replace(controls, power="on" if on else "off"))

    async def apps(self, device_id: str) -> list[AppInfo]:
        if not self._live(device_id).apps:
            raise ControlError(CANT_DO_THAT)
        await self._sleep(self._delay / 2)
        return list(DEMO_APPS)

    async def launch_app(self, device_id: str, app_id: str) -> None:
        controls = self._live(device_id)
        app = next((a for a in DEMO_APPS if a.id == app_id), None)
        if not controls.apps or app is None:
            raise ControlError(CANT_DO_THAT)
        self.launched.append((device_id, app_id))
        playing = controls.now_playing
        if playing is not None:
            playing = replace(playing, app=app.name)
        self._set_controls(
            device_id, replace(controls, now_playing=playing, keyboard=app_id == SEARCH_APP)
        )

    async def set_text(self, device_id: str, text: str) -> None:
        if not self._live(device_id).text_entry:
            raise ControlError(CANT_DO_THAT)
        self.texts.append((device_id, text[:MAX_TEXT]))

    # What the PC is playing

    def music(self) -> MusicSnapshot | None:
        return self._music

    def music_artwork(self) -> MusicArtwork | None:
        if self._music is None:
            return None
        return MusicArtwork(_demo_artwork(DEMO_TRACKS[self._track][4]), "image/svg+xml")

    async def music_command(self, command: MusicCommand) -> None:
        music = self._music
        if music is None:
            raise ControlError(NOTHING_PLAYING)
        if command is MusicCommand.PLAY_PAUSE:
            state = "paused" if music.state == "playing" else "playing"
            self._set_music(self._track_snapshot(state, self._position_now(music)))
            return
        step = 1 if command is MusicCommand.NEXT else -1
        self._track = (self._track + step) % len(DEMO_TRACKS)
        self._artwork_id += 1
        self._set_music(self._track_snapshot(music.state, 0.0))

    async def music_seek(self, position: float) -> None:
        music = self._music
        if music is None:
            raise ControlError(NOTHING_PLAYING)
        length = DEMO_TRACKS[self._track][3]
        self._set_music(self._track_snapshot(music.state, min(max(0.0, position), length)))

    def stop_music(self) -> None:
        """The demo app closes, as if nothing played on the PC (used by tests)."""
        self._set_music(None)

    def _track_snapshot(self, state: str, position: float) -> MusicSnapshot:
        title, artist, album, length, _colours = DEMO_TRACKS[self._track]
        return MusicSnapshot(
            app=DEMO_MUSIC_APP,
            state=state,
            title=title,
            artist=artist,
            album=album,
            position=position,
            duration=length,
            position_at=self._clock(),
            commands=frozenset(MusicCommand),
            can_seek=True,
            artwork=self._artwork_id,
        )

    def _position_now(self, music: MusicSnapshot) -> float:
        position = music.position or 0.0
        if music.state == "playing":
            position += self._clock() - music.position_at
        return min(position, music.duration or position)

    def _set_music(self, music: MusicSnapshot | None) -> None:
        self._music = music
        self._publish(MusicChanged(music))

    # Typed commands

    def preview_command(self, text: str) -> CommandOutcome:
        if self.commands is None:
            return CommandOutcome("notAvailable", "noCommands")
        return self.commands.preview_command(text)

    async def run_command(self, text: str) -> CommandOutcome:
        if self.commands is None:
            return CommandOutcome("notAvailable", "noCommands")
        return await self.commands.run_command(text)

    def remove(self, device_id: str) -> None:
        """Forget a device, as if it left the network (used by tests)."""
        if self._devices.pop(device_id, None) is not None:
            self._publish(DeviceRemoved(device_id))

    def _publish(self, event: BackendEvent) -> None:
        for listener in list(self._listeners):
            listener(event)


def _load_appearance(path: Path | None) -> Appearance:
    if path is None or not path.exists():
        return Appearance()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Appearance(
            Theme(data["theme"]),
            str(data["background"]),
            bool(data.get("appIcons", True)),
            bool(data.get("onboarded", False)),
            update_check=bool(data.get("updateCheck", True)),
            restore_outputs=bool(data.get("restoreOutputs", False)),
            photo_blur=int(data.get("photoBlur", 0)),
        )
    except (OSError, ValueError, KeyError, TypeError):
        _LOGGER.warning("Ignoring an unreadable appearance file; using the defaults")
        return Appearance()


def _save_appearance(path: Path, appearance: Appearance) -> None:
    data = {
        "theme": appearance.theme.value,
        "background": appearance.background,
        "appIcons": appearance.app_icons,
        "onboarded": appearance.onboarded,
        "updateCheck": appearance.update_check,
        "restoreOutputs": appearance.restore_outputs,
        "photoBlur": appearance.photo_blur,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        _LOGGER.warning("Couldn't save the appearance setting")


class _DemoPairing:
    def __init__(self, steps: int, finish: Callable[[str, bool], Awaitable[None]]) -> None:
        self._steps = steps
        self._done = 0
        self._finish = finish

    @property
    def steps(self) -> int:
        return self._steps

    async def submit_pin(self, pin: str) -> bool:
        last = self._done + 1 == self._steps
        await self._finish(pin, last)
        self._done += 1
        return not last

    async def cancel(self) -> None:
        return None
