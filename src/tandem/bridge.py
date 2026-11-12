"""The real engine behind the window: the UI's `Backend` contract (ADR-0008) on `Engine`.

This is the one module that imports both `tandem.engine` and `tandem.ui`; the two layers
never import each other. `DemoBackend` is the same bridge on invented devices (ADR-0019).
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from tandem.bridge_audio import EngineAudio
from tandem.bridge_home import EngineHome
from tandem.bridge_library import EngineLibrary
from tandem.bridge_network import EngineNetwork
from tandem.bridge_spotify import EngineSpotify
from tandem.engine import control as ec
from tandem.engine import pairing as engine_pairing
from tandem.engine import paths
from tandem.engine.apple_catalog import AppleCatalog
from tandem.engine.command_dispatch import (
    CommandDispatcher,
    CommandResult,
    EngineCommandServices,
)
from tandem.engine.events import EventBus
from tandem.engine.home_bridge import BridgeServer
from tandem.engine.library import MusicLibrary
from tandem.engine.models import Device, Service
from tandem.engine.output_groups import GroupStore
from tandem.engine.output_prefs import OutputPrefsStore
from tandem.engine.pc_media import PcMediaCommand, PcNowPlaying, PcNowPlayingChanged
from tandem.engine.radio import Radio
from tandem.engine.registry import DeviceEvent, DeviceLost
from tandem.engine.service import Engine, UnknownDeviceError
from tandem.engine.session import ConnectionState, ConnectionStateChanged
from tandem.engine.settings import SettingsChanged, SettingsStore
from tandem.engine.settings import Theme as EngineTheme
from tandem.engine.spotify import Spotify
from tandem.ui import backend as ui

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

# Gives up after this many failed attempts in a row; the card then offers "Try again".
MAX_ATTEMPTS = 6

# How pyatv reports a PIN the device rejected (an exception type name, or the engine's own).
_WRONG_PIN = {engine_pairing.NOT_PAIRED, "PairingError", "AuthenticationError"}

Problem = ui.Problem

_PC_MEDIA = {
    ui.MusicCommand.PLAY_PAUSE: PcMediaCommand.PLAY_PAUSE,
    ui.MusicCommand.NEXT: PcMediaCommand.NEXT,
    ui.MusicCommand.PREVIOUS: PcMediaCommand.PREVIOUS,
}

_MEDIA = {
    ui.MediaCommand.NEXT: ec.MediaCommand.NEXT,
    ui.MediaCommand.PREVIOUS: ec.MediaCommand.PREVIOUS,
    ui.MediaCommand.SKIP_FORWARD: ec.MediaCommand.SKIP_FORWARD,
    ui.MediaCommand.SKIP_BACKWARD: ec.MediaCommand.SKIP_BACKWARD,
}
_MEDIA_NEEDS = {
    ui.MediaCommand.NEXT: ec.Capability.NEXT,
    ui.MediaCommand.PREVIOUS: ec.Capability.PREVIOUS,
    ui.MediaCommand.SKIP_FORWARD: ec.Capability.SKIP_FORWARD,
    ui.MediaCommand.SKIP_BACKWARD: ec.Capability.SKIP_BACKWARD,
}
_FAILURE = {
    ec.Failure.NOT_CONNECTED: Problem.NOT_CONNECTED,
    ec.Failure.NO_TEXT_FIELD: Problem.NO_TEXT_FIELD,
    ec.Failure.CANT_DO_THAT: Problem.CANT_DO_THAT,
    ec.Failure.NO_RESPONSE: Problem.NO_RESPONSE,
}

_LINK = {
    ConnectionState.DISCONNECTED: ui.LinkState.DISCONNECTED,
    ConnectionState.CONNECTING: ui.LinkState.CONNECTING,
    ConnectionState.CONNECTED: ui.LinkState.CONNECTED,
    ConnectionState.WAITING: ui.LinkState.WAITING,
    ConnectionState.FAILED: ui.LinkState.FAILED,
}


@dataclass(frozen=True, slots=True)
class _Link:
    state: ui.LinkState = ui.LinkState.DISCONNECTED
    retry_in: float | None = None


class EngineBackend(EngineAudio, EngineLibrary, EngineSpotify, EngineHome, EngineNetwork):
    def __init__(
        self,
        engine: Engine,
        settings: SettingsStore,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        pin_timeout: float = engine_pairing.DEFAULT_PIN_TIMEOUT,
        home_server: Callable[[], BridgeServer] | None = None,
        library: MusicLibrary | None = None,
        radio: Radio | None = None,
        catalog: AppleCatalog | None = None,
        spotify: Spotify | None = None,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._max_attempts = max_attempts
        self._pin_timeout = pin_timeout
        self._listeners: list[ui.Listener] = []
        self._links: dict[str, _Link] = {}
        self._status: dict[str, ec.ControlStatus] = {}
        bus = engine.bus
        self._unsubscribe = [
            bus.subscribe(DeviceEvent, self._on_device),
            bus.subscribe(ConnectionStateChanged, self._on_connection),
            bus.subscribe(SettingsChanged, self._on_settings),
            bus.subscribe(ec.ControlEvent, self._on_control),
            bus.subscribe(PcNowPlayingChanged, self._on_pc_media),
        ]
        self._unsubscribe += self._init_audio()
        self._unsubscribe += self._init_home(home_server)
        self._init_network()
        self._unsubscribe += self._init_library(library, radio, catalog)
        self._unsubscribe += self._init_spotify(spotify)
        engine.outputs.pc_mute.enabled = settings.settings.mute_pc
        self._commands = CommandDispatcher(EngineCommandServices(engine, home=self.home_bridge))

    # Observing

    def subscribe(self, listener: ui.Listener) -> ui.Unsubscribe:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def devices(self) -> list[ui.DeviceSnapshot]:
        return [self._snapshot(d) for d in self._engine.registry.devices()]

    def appearance(self) -> ui.Appearance:
        settings = self._settings.settings
        background = settings.background
        if background not in ui.BACKGROUNDS:
            background = ui.Appearance().background
        return ui.Appearance(
            ui.Theme(settings.theme.value),
            background,
            settings.app_icons,
            settings.onboarded,
            update_check=settings.update_check,
            restore_outputs=settings.restore_outputs,
            mute_pc=settings.mute_pc,
            photo_blur=settings.photo_blur,
        )

    def controls(self, device_id: str) -> ui.ControlsSnapshot | None:
        status = self._status.get(device_id)
        return None if status is None else _controls(status)

    def music(self) -> ui.MusicSnapshot | None:
        return _music(self._engine.pc_media.now_playing)

    def music_artwork(self) -> ui.MusicArtwork | None:
        art = self._engine.pc_media.artwork()
        return None if art is None else ui.MusicArtwork(art.data, art.mimetype)

    # Lifecycle

    async def start(self) -> None:
        await self._engine.open()
        self._engine.pc_media.start()  # what the PC's apps are playing (Phase 6)
        self._publish(ui.DiscoveryChanged(active=True))
        try:
            await self._engine.scan()
        except Exception as exc:
            _LOGGER.warning("First discovery scan failed (%s)", type(exc).__name__)
        finally:
            self._publish(ui.DiscoveryChanged(active=False))
        self._engine.discovery.start()
        self._engine.start_network_watch()
        await self._engine.start_speaker_buttons()
        if self._settings.settings.restore_outputs:
            self.restore_outputs()
        await self._start_home()
        await self._start_library()
        await self._start_spotify()

    async def stop(self) -> None:
        await self._stop_home()
        await self._stop_library()
        await self._stop_spotify()
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe = []
        await self._engine.close()

    # Commands

    async def connect(self, device_id: str) -> None:
        device = self._device(device_id)
        if engine_pairing.services_to_pair(device):
            raise ui.PairingError(Problem.PAIR_FIRST)
        # Start and return: progress arrives as ConnectionStateChanged events.
        self._engine.session(device_id, max_attempts=self._max_attempts).start()

    async def disconnect(self, device_id: str) -> None:
        await self._engine.disconnect(device_id)
        self._set_link(device_id, _Link())

    async def begin_pairing(self, device_id: str) -> ui.PairingFlow:
        device = self._device(device_id)
        services = engine_pairing.services_to_pair(device)
        if not services:
            raise ui.PairingError(Problem.NO_PAIRING_NEEDED)
        flow = _EnginePairing(self._engine, device_id, services, self._pin_timeout)
        await flow.start()
        return flow

    async def press(self, device_id: str, key: ui.RemoteKey, action: ui.KeyAction) -> None:
        controls = self._engine.controls(device_id)
        await _control(controls.press(ec.RemoteKey(key.value), ec.KeyAction(action.value)))

    async def media(self, device_id: str, command: ui.MediaCommand) -> None:
        controls = self._engine.controls(device_id)
        if command is ui.MediaCommand.PLAY_PAUSE:
            await _control(controls.play_pause())
        else:
            await _control(controls.media(_MEDIA[command]))

    async def set_volume(self, device_id: str, level: float) -> None:
        await _control(self._engine.controls(device_id).set_volume(level))

    async def set_power(self, device_id: str, on: bool) -> None:
        await _control(self._engine.controls(device_id).set_power(on))

    async def apps(self, device_id: str) -> list[ui.AppInfo]:
        found = await _control(self._engine.controls(device_id).apps())
        return [ui.AppInfo(app.id, app.name) for app in found]

    async def launch_app(self, device_id: str, app_id: str) -> None:
        await _control(self._engine.controls(device_id).launch(app_id))

    async def set_text(self, device_id: str, text: str) -> None:
        await _control(self._engine.controls(device_id).set_text(text[: ui.MAX_TEXT]))

    async def music_command(self, command: ui.MusicCommand) -> None:
        music = self.music()
        if music is None:
            raise ui.ControlError(Problem.NOTHING_PLAYING)
        if command not in music.commands:
            raise ui.ControlError(Problem.APP_CANT)
        if not await self._engine.pc_media.command(_PC_MEDIA[command]):
            raise ui.ControlError(Problem.APP_DIDNT_RESPOND)

    async def music_seek(self, position: float) -> None:
        music = self.music()
        if music is None:
            raise ui.ControlError(Problem.NOTHING_PLAYING)
        if not music.can_seek or position < 0:
            raise ui.ControlError(Problem.APP_CANT)
        if not await self._engine.pc_media.seek(position):
            raise ui.ControlError(Problem.APP_DIDNT_RESPOND)

    async def set_appearance(self, appearance: ui.Appearance) -> None:
        # The store publishes SettingsChanged on the engine's bus, which `_on_settings` relays.
        self._settings.update(
            theme=EngineTheme(appearance.theme.value),
            background=appearance.background,
            app_icons=appearance.app_icons,
            onboarded=appearance.onboarded,
            update_check=appearance.update_check,
            restore_outputs=appearance.restore_outputs,
            mute_pc=appearance.mute_pc,
            photo_blur=appearance.photo_blur,
        )

    def preview_command(self, text: str) -> ui.CommandOutcome:
        return _outcome(self._commands.preview(text))

    async def run_command(self, text: str) -> ui.CommandOutcome:
        return _outcome(await self._commands.run(text))

    async def set_window_visible(self, visible: bool) -> None:
        # Hidden and silent: scan once a minute instead of every few seconds.
        idle = not visible and not self._engine.outputs_on()
        await self._engine.discovery.set_idle(idle)

    async def write_diagnostics(self) -> Path | None:
        settings = self._settings.settings.to_json()
        return await asyncio.to_thread(
            self._engine.diagnostics,
            paths.data_dir() / "diagnostics",
            log_dir=paths.log_dir(),
            settings=settings,
        )

    # Engine events

    def _on_device(self, event: DeviceEvent) -> None:
        if isinstance(event, DeviceLost):
            self._links.pop(event.device.id, None)
            self._publish(ui.DeviceRemoved(event.device.id))
        else:
            self._publish(ui.DeviceUpdated(self._snapshot(event.device)))

    def _on_connection(self, event: ConnectionStateChanged) -> None:
        self._set_link(event.device_id, _Link(_LINK[event.state], event.retry_in))

    def _on_settings(self, event: SettingsChanged) -> None:
        self._engine.outputs.set_pc_mute(self._settings.settings.mute_pc)
        self._publish(ui.AppearanceChanged(self.appearance()))

    def _on_pc_media(self, event: PcNowPlayingChanged) -> None:
        self._publish(ui.MusicChanged(_music(event.now_playing)))

    def _on_control(self, event: ec.ControlEvent) -> None:
        device_id = event.device_id
        if isinstance(event, ec.ControlsUnavailable):
            if self._status.pop(device_id, None) is not None:
                self._publish(ui.ControlsChanged(device_id, None))
            return
        if isinstance(event, ec.ControlsAvailable):
            status = event.status
        else:
            current = self._status.get(device_id)
            if current is None:
                return  # an update before the controls were announced
            if isinstance(event, ec.NowPlayingChanged):
                status = dataclasses.replace(current, now_playing=event.now_playing)
            elif isinstance(event, ec.CapabilitiesChanged):
                status = dataclasses.replace(
                    current, capabilities=event.capabilities, volume_control=event.volume_control
                )
            elif isinstance(event, ec.PowerChanged):
                status = dataclasses.replace(current, power=event.power)
            elif isinstance(event, ec.VolumeChanged):
                status = dataclasses.replace(current, volume=event.volume)
            elif isinstance(event, ec.KeyboardChanged):
                status = dataclasses.replace(current, keyboard=event.focused)
            else:
                return
        self._status[device_id] = status
        self._publish(ui.ControlsChanged(device_id, _controls(status)))

    # Internals

    def _device(self, device_id: str) -> Device:
        try:
            return self._engine.device(device_id)
        except UnknownDeviceError:
            raise ui.PairingError(Problem.NOT_AVAILABLE) from None

    def _set_link(self, device_id: str, link: _Link) -> None:
        self._links[device_id] = link
        device = self._engine.registry.get(device_id)
        if device is not None:
            self._publish(ui.DeviceUpdated(self._snapshot(device)))

    def _snapshot(self, device: Device) -> ui.DeviceSnapshot:
        link = self._links.get(device.id, _Link())
        return ui.DeviceSnapshot(
            id=device.id,
            name=device.name,
            kind=ui.DeviceKind(device.kind.value),
            state=link.state,
            needs_pairing=bool(engine_pairing.services_to_pair(device)),
            retry_in=link.retry_in if link.state is ui.LinkState.WAITING else None,
        )

    def _publish(self, event: ui.BackendEvent) -> None:
        for listener in list(self._listeners):
            listener(event)


class _EnginePairing:
    """Pairs each service in turn; each one makes the device show a new PIN.

    The engine's `pair` asks for the PIN through a callback. Here that callback signals that
    the device is now showing a PIN, then waits for the user to type it into the window.
    """

    def __init__(
        self, engine: Engine, device_id: str, services: list[Service], pin_timeout: float
    ) -> None:
        self._engine = engine
        self._device_id = device_id
        self._services = list(services)
        self._pin_timeout = pin_timeout
        self._index = 0
        self._task: asyncio.Task[None] | None = None
        self._pin: asyncio.Future[str] | None = None

    @property
    def steps(self) -> int:
        return len(self._services)

    async def start(self) -> None:
        await self._show_next_pin()

    async def submit_pin(self, pin: str) -> bool:
        task, future = self._task, self._pin
        if task is None or future is None:
            return False  # everything paired without a PIN
        if not future.done():
            future.set_result(pin)
        try:
            await task
        except engine_pairing.PairingError as error:
            if error.reason in _WRONG_PIN:
                await self._show_next_pin()  # the same service again: the device shows a new PIN
                raise ui.WrongPinError(Problem.WRONG_PIN) from None
            raise ui.PairingError(_message(error.reason)) from None
        self._index += 1
        return await self._show_next_pin()

    async def cancel(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError, engine_pairing.PairingError):
                await task

    async def _show_next_pin(self) -> bool:
        """Start pairing the current service. True once the device shows a PIN; False when
        nothing is left. Services that pair without a PIN are finished on the way."""
        loop = asyncio.get_running_loop()
        while self._index < len(self._services):
            service = self._services[self._index]
            showing: asyncio.Future[None] = loop.create_future()
            pin: asyncio.Future[str] = loop.create_future()

            async def provide(
                showing: asyncio.Future[None] = showing, pin: asyncio.Future[str] = pin
            ) -> str:
                if not showing.done():
                    showing.set_result(None)
                return await pin

            task = loop.create_task(
                self._engine.pair(
                    self._device_id,
                    service,
                    provide,
                    pin_timeout=self._pin_timeout,
                )
            )
            self._task, self._pin = task, pin
            await asyncio.wait({showing, task}, return_when=asyncio.FIRST_COMPLETED)
            if showing.done():
                return True
            try:
                task.result()
            except engine_pairing.PairingError as error:
                raise ui.PairingError(_message(error.reason)) from None
            self._index += 1  # paired without a PIN
        self._task, self._pin = None, None
        return False


async def _control(command: Awaitable[T]) -> T:
    """Run a control command, turning engine errors into problem codes for the window."""
    try:
        return await command
    except Exception as error:
        failure = ec.failure_of(error)
        if failure is None:
            raise
        raise ui.ControlError(_FAILURE[failure]) from None


def _controls(status: ec.ControlStatus) -> ui.ControlsSnapshot:
    caps = status.capabilities
    media = {command for command, needs in _MEDIA_NEEDS.items() if needs in caps}
    if status.can_play or status.can_pause:
        media.add(ui.MediaCommand.PLAY_PAUSE)
    playing = status.now_playing
    now_playing = None
    if ec.Capability.NOW_PLAYING in caps:
        now_playing = ui.NowPlayingSnapshot(
            state=playing.state.value,
            title=playing.title,
            artist=playing.artist,
            album=playing.album,
            series=playing.series,
            app=playing.app_name,
            position=playing.position,
            total_time=playing.total_time,
        )
    return ui.ControlsSnapshot(
        remote=ec.Capability.REMOTE in caps,
        media=frozenset(media),
        volume=ui.Volume(status.volume_control.value),
        volume_level=status.volume if status.volume_control is ec.VolumeControl.LEVEL else None,
        power=status.power.value,
        can_power=ec.Capability.POWER in caps,
        now_playing=now_playing,
        apps=ec.Capability.APPS in caps,
        text_entry=ec.Capability.TEXT_ENTRY in caps,
        keyboard=status.keyboard and ec.Capability.TEXT_ENTRY in caps,
    )


def _music(playing: PcNowPlaying | None) -> ui.MusicSnapshot | None:
    if playing is None:
        return None
    allowed = {
        ui.MusicCommand.PLAY_PAUSE: playing.can_play_pause,
        ui.MusicCommand.NEXT: playing.can_next,
        ui.MusicCommand.PREVIOUS: playing.can_previous,
    }
    return ui.MusicSnapshot(
        app=playing.app,
        state=playing.state,
        title=playing.title,
        artist=playing.artist,
        album=playing.album,
        position=playing.position,
        duration=playing.duration,
        position_at=playing.position_at,
        commands=frozenset(command for command, on in allowed.items() if on),
        can_seek=playing.can_seek,
        artwork=playing.artwork_id,
    )


def _outcome(result: CommandResult) -> ui.CommandOutcome:
    return ui.CommandOutcome(
        result.outcome.value, result.code, dict(result.params), result.suggestions
    )


def _message(reason: str) -> str:
    return Problem.PIN_EXPIRED if reason == engine_pairing.PIN_TIMEOUT else Problem.COULD_NOT_PAIR


class DemoBackend(EngineBackend):
    """The real bridge and engine on invented devices: `--demo`, screenshots and the window's
    tests (ADR-0019). `demo` is the device adapter, for tests that look at what was sent.

    `sleep` sets how long the invented devices take to answer; `engine_sleep` is the engine's
    own (retries, discovery). Settings live in `settings_file`, or in memory without one.
    """

    def __init__(
        self,
        *,
        settings_file: Path | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        engine_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        delay: float = 0.6,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        from tandem.engine.adapters.demo import DemoBridgeServer, DemoDevices

        self.demo = DemoDevices(sleep=sleep, delay=delay, clock=clock)
        bus = EventBus()
        store = SettingsStore(settings_file, bus)
        if settings_file is not None:
            store.load()
        engine = Engine(
            self.demo, bus=bus, sleep=engine_sleep, clock=clock, discovery_interval=30.0
        )
        music = self.demo.music
        library = MusicLibrary(
            bus,
            store=None,
            list_files=music.list_files,
            read_tags=music.read_tags,
            read_art=music.read_art,
        )
        catalog = AppleCatalog(
            bus,
            music.search_catalog,
            music.fetch_image,
            music.open_link,
            fetch_badge=music.fetch_badge,
            clock=clock,
        )
        from tandem.engine.adapters.demo_spotify import DemoSpotifyWeb

        self.spotify_web = DemoSpotifyWeb(sleep=sleep, delay=delay)
        web = self.spotify_web
        super().__init__(
            engine,
            store,
            home_server=DemoBridgeServer,
            library=library,
            radio=Radio(bus, music.search_stations, store=None),
            catalog=catalog,
            spotify=Spotify(bus, web, web, web.open_url, web.listen, clock=clock),
        )

    async def start(self) -> None:
        await super().start()
        if self._library is not None:
            from tandem.engine.adapters.demo_music import DEMO_FOLDER

            await self._library.add_folder(DEMO_FOLDER)  # the invented albums
            await self._library.wait_idle()  # so the demo starts in a settled state

    async def write_diagnostics(self) -> Path | None:
        return None  # invented devices: nothing worth reporting, and no real logs to read

    def remove(self, device_id: str) -> None:
        """A device leaves the network (used by tests)."""
        self.demo.remove(device_id)
        self._engine.registry.remove(device_id)

    def stop_music(self) -> None:
        """The demo music app closes (used by tests)."""
        self.demo.sessions.close_app()


def create_engine_backend() -> EngineBackend:  # pragma: no cover - needs the network
    """The engine as the app runs it: pyatv, the DPAPI credential vault, redacted file logs."""
    from tandem.engine import paths
    from tandem.engine.adapters.credential_vault import CredentialVault
    from tandem.engine.adapters.pyatv_adapter import PyatvBackend
    from tandem.engine.adapters.pyatv_dacp import ZeroconfAdvertiser
    from tandem.engine.addresses import AddressStore
    from tandem.engine.logs import configure_logging
    from tandem.engine.network import NetworkWatch
    from tandem.engine.redact import Redactor
    from tandem.engine.speaker_buttons import SpeakerButtons

    redactor = Redactor()
    configure_logging(redactor, log_dir=paths.log_dir())
    bus = EventBus()
    store = SettingsStore(paths.settings_file(), bus)
    settings = store.load()
    prefs = OutputPrefsStore(paths.data_dir() / "outputs.json")
    prefs.load()
    groups = GroupStore(paths.data_dir() / "groups.json")
    groups.load()
    addresses = AddressStore(paths.data_dir() / "addresses.json")
    addresses.load()
    engine = Engine(
        PyatvBackend(CredentialVault(paths.credentials_file())),
        bus=bus,
        redactor=redactor,
        discovery_interval=settings.discovery_interval_s,
        output_prefs=prefs,
        output_groups=groups,
        addresses=addresses,
        network_watch=NetworkWatch(),
        speaker_buttons=SpeakerButtons(ZeroconfAdvertiser()),
    )

    def home_server() -> BridgeServer:
        from tandem.engine.adapters.hap_bridge import HapBridgeServer

        return HapBridgeServer(paths.data_dir() / "home-bridge.state")

    from tandem.engine.adapters.library_files import list_files, read_art, read_tags
    from tandem.engine.adapters.radio_browser import search_stations

    library = MusicLibrary(
        bus,
        store=paths.data_dir() / "library.json",
        list_files=list_files,
        read_tags=read_tags,
        read_art=read_art,
    )
    radio = Radio(bus, search_stations, store=paths.data_dir() / "radio.json")
    from tandem.engine.adapters.itunes_catalog import (
        badge_fetcher,
        fetch_image,
        open_in_apple_music,
        search_catalog,
    )
    from tandem.ui.platform import store_country

    country = store_country()
    catalog = AppleCatalog(
        bus,
        search_catalog,
        fetch_image,
        open_in_apple_music,
        fetch_badge=badge_fetcher(country),
        country=country,
    )
    return EngineBackend(
        engine,
        store,
        home_server=home_server,
        library=library,
        radio=radio,
        catalog=catalog,
        spotify=create_spotify(bus),
    )


def create_spotify(bus: EventBus) -> Spotify:  # pragma: no cover - needs the network
    """Spotify as the app runs it: aiohttp, the system browser, a DPAPI-encrypted file."""
    from tandem.engine import paths
    from tandem.engine.adapters.spotify_web import AiohttpSpotifyHttp, listen, open_in_browser
    from tandem.engine.vault import EncryptedJsonFile

    return Spotify(
        bus,
        AiohttpSpotifyHttp(),
        EncryptedJsonFile(paths.data_dir() / "spotify.bin"),
        open_in_browser,
        listen,
    )
