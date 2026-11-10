"""The engine's service API: what the UI and the developer tool call.

`Engine` ties discovery, the registry, pairing and connection sessions together on top of a
`Backend`, which does the protocol work (pyatv, in `adapters`). Everything here is
protocol-agnostic and tested with a fake backend.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from tandem.engine import diagnostics, lineup, net_check, pairing
from tandem.engine.addresses import AddressError, AddressStore, normalize
from tandem.engine.audio import (
    AudioError,
    AudioSink,
    AudioStats,
    AudioStreamChanged,
    PcmCapture,
    StreamState,
)
from tandem.engine.audio_hub import AudioHub, is_local
from tandem.engine.control import Controller, DeviceControls
from tandem.engine.control_hub import ControlHub
from tandem.engine.discovery import Discovery, Sleep
from tandem.engine.events import EventBus
from tandem.engine.media_send import (
    MediaError,
    MediaSender,
    MediaSends,
    MediaServer,
    check_playable,
    is_link,
    local_address_towards,
    title_for,
)
from tandem.engine.models import Device, LocalOutput, Service
from tandem.engine.network import NetworkWatch
from tandem.engine.output_groups import GroupStore
from tandem.engine.output_prefs import OutputPrefsStore
from tandem.engine.outputs import Outputs
from tandem.engine.pairing import PairingError, PairingFactory, PinProvider
from tandem.engine.pc_media import MediaSessions, PcMediaCommand, PcMediaWatcher
from tandem.engine.pc_mute import PcMute, SpeakerMute
from tandem.engine.player import DecodedStream, Player, Track
from tandem.engine.redact import Redactor
from tandem.engine.registry import DeviceRegistry
from tandem.engine.session import ConnectionSession, Connector, Link
from tandem.engine.speaker_buttons import ButtonCommand, ButtonPress, SpeakerButtons

_LOGGER = logging.getLogger(__name__)


class Backend(Protocol):
    async def load(self) -> None:
        """Load stored credentials."""

    async def save(self) -> None:
        """Persist credentials changed by pairing or forgetting."""

    async def scan(self, timeout: float) -> Sequence[Device]: ...

    async def scan_hosts(self, hosts: Sequence[str], timeout: float) -> Sequence[Device]:
        """Ask these addresses directly (unicast) instead of the whole network."""
        ...

    async def set_password(self, device_id: str, password: str) -> None:
        """Save a speaker's password with its credentials."""
        ...

    async def describe(self, device_id: str) -> Device | None:
        """The device as last scanned, with current pairing state; None if not scanned."""
        ...

    def pairing(self, device_id: str, service: Service) -> PairingFactory: ...
    def connector(self, device_id: str) -> Connector: ...

    async def forget(self, device_id: str) -> bool:
        """Delete the device's stored credentials. Returns False if there were none."""
        ...

    def controller(self, link: Link) -> Controller | None:
        """Remote and media controls on an open link; None if the device has none."""
        ...

    def audio_sink(self, link: Link) -> AudioSink | None:
        """Streams PCM to the device on an open link; None if it takes no audio."""
        ...

    def capture(self) -> PcmCapture:
        """A fresh capture of the PC's own audio."""
        ...

    def local_outputs(self) -> Sequence[LocalOutput]:
        """The PC's own sound outputs (speakers, headphones)."""
        ...

    def local_sink(self, output_id: str) -> AudioSink | None:
        """Plays to one of the PC's sound outputs; None if it's gone."""
        ...

    def media_sender(self, link: Link) -> MediaSender | None:
        """Plays a URL on the device on an open link; None if it can't play video."""
        ...

    def open_track(self, track: Track) -> DecodedStream:
        """Decode a music file or a radio stream for the player."""
        ...

    def media_sessions(self) -> MediaSessions:
        """Windows' media controls: what the PC's apps are playing."""
        ...

    def microphone(self) -> PcmCapture:
        """The default microphone as 16 kHz mono PCM (for lining speakers up)."""
        ...

    def speaker_mute(self) -> SpeakerMute | None:
        """Mutes the PC's default output without silencing the capture; None if it can't."""
        ...


AUDIO_CONNECT_TIMEOUT = 15.0
"""Seconds to wait for a speaker before saying it couldn't play (it normally takes one)."""


VOLUME_STEP = 5.0
"""How far a speaker's volume key moves its volume in Tandem (0 to 100)."""

_VOLUME_BUTTONS = {ButtonCommand.VOLUME_UP, ButtonCommand.VOLUME_DOWN, ButtonCommand.VOLUME}
_PC_BUTTONS = {
    ButtonCommand.PLAY_PAUSE: PcMediaCommand.PLAY_PAUSE,
    ButtonCommand.NEXT: PcMediaCommand.NEXT,
    ButtonCommand.PREVIOUS: PcMediaCommand.PREVIOUS,
}


class AudioSource(Enum):
    SYSTEM = "system"
    """The PC's own audio (loopback of the default output)."""
    PLAYER = "player"
    """Tandem's player: local files and internet radio."""


class UnknownDeviceError(LookupError):
    """No device with that id has been discovered."""


SERVICE_NOT_OFFERED = "ServiceNotOffered"


class Engine:
    def __init__(
        self,
        backend: Backend,
        *,
        bus: EventBus | None = None,
        redactor: Redactor | None = None,
        discovery_interval: float = 10.0,
        scan_timeout: float = 3.0,
        sleep: Sleep = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        output_prefs: OutputPrefsStore | None = None,
        output_groups: GroupStore | None = None,
        pc_mute_record: Path | None = None,
        addresses: AddressStore | None = None,
        network_watch: NetworkWatch | None = None,
        network_probe: net_check.Probe | None = None,
        speaker_buttons: SpeakerButtons | None = None,
    ) -> None:
        self.bus = bus or EventBus()
        self.redactor = redactor or Redactor()
        self.registry = DeviceRegistry(self.bus, self.redactor, clock)
        self._backend = backend
        self._sleep = sleep
        self._clock = clock
        self.addresses = addresses or AddressStore(None)
        """Speakers the user added by address (for networks that hide them)."""
        for address in self.addresses.addresses():
            self.redactor.add(address, "address")
        self.scans = net_check.ScanHistory()
        """What recent discovery scans found, for the network check."""
        self.network_watch = network_watch
        """Notices network changes; None leaves it to the next scan."""
        self._network_probe = network_probe
        self.speaker_buttons = speaker_buttons
        """Receives a speaker's own play, pause, skip and volume buttons; None turns it off."""
        self.discovery = Discovery(
            self.registry,
            self._scan,
            interval=discovery_interval,
            scan_timeout=scan_timeout,
            sleep=sleep,
        )
        self._sessions: dict[str, ConnectionSession] = {}
        self._controls = ControlHub(self.bus, backend.controller, self._live_link)
        self.player = Player(self.bus, backend.open_track)
        self.audio_source = AudioSource.SYSTEM
        self.audio_connect_timeout = AUDIO_CONNECT_TIMEOUT
        """How long `start_output` waits for a speaker to connect."""
        self._audio = AudioHub(
            self.bus,
            backend.capture,
            backend.audio_sink,
            self._live_link,
            local_sink=backend.local_sink,
        )
        self.pc_media = PcMediaWatcher(self.bus, backend.media_sessions(), clock=clock)
        self._media_server: MediaServer | None = None
        self._sends = MediaSends(self.bus.publish)
        self.outputs = Outputs(
            self, output_prefs, output_groups, PcMute(backend.speaker_mute(), pc_mute_record)
        )
        """Outputs as the user sees them: switch them here, not with `start_output`."""
        self.bus.subscribe(AudioStreamChanged, self._on_stream)

    def _on_stream(self, event: AudioStreamChanged) -> None:
        # A stalled stream usually means a dead connection that hasn't noticed: reconnect,
        # and the stream resumes on the fresh connection.
        if event.reason == "Stalled" and not is_local(event.device_id):
            session = self._sessions.get(event.device_id)
            if session is not None:
                session.reconnect()

    def _live_link(self, device_id: str) -> Link | None:
        session = self._sessions.get(device_id)
        return session.link if session else None

    def controls(self, device_id: str) -> DeviceControls:
        """Remote, media, volume and power controls for a device. They work while it is
        connected (see `connect`) and raise NotConnectedError otherwise."""
        return self._controls.controls(device_id)

    async def open(self) -> None:
        await self._backend.load()
        await self.outputs.pc_mute.recover()  # a previous run stopped with the PC muted

    async def close(self) -> None:
        """Stop discovery and disconnect everything."""
        if self.network_watch is not None:
            await self.network_watch.stop()
        if self.speaker_buttons is not None:
            await self.speaker_buttons.stop()
        await self.outputs.close()
        await self.discovery.stop()
        await self._sends.close()
        if self._media_server is not None:
            await self._media_server.stop()
        await self.pc_media.stop()
        await self.player.close()
        await self._audio.close()
        for device_id in list(self._sessions):
            await self.disconnect(device_id)
        await self._controls.close()

    async def _scan(self, timeout: float) -> list[Device]:
        """One discovery scan: the whole network, plus the saved addresses asked directly."""
        hosts = self.addresses.addresses()
        if not hosts:
            found = list(await self._backend.scan(timeout))
            self.scans.record(len(found), 0)
            return found
        multicast, unicast = await asyncio.gather(
            self._backend.scan(timeout),
            self._backend.scan_hosts(hosts, timeout),
            return_exceptions=True,
        )
        if isinstance(multicast, BaseException):
            raise multicast
        found = list(multicast)
        extra: list[Device] = [] if isinstance(unicast, BaseException) else list(unicast)
        self.scans.record(len(found), len(extra))
        known = {d.id for d in found}
        return found + [d for d in extra if d.id not in known]

    async def scan(self) -> list[Device]:
        """Scan once and return every visible device."""
        await self.discovery.scan_once()
        return self.registry.devices()

    def device(self, device_id: str) -> Device:
        device = self.registry.get(device_id)
        if device is None:
            raise UnknownDeviceError(device_id)
        return device

    async def pair(
        self,
        device_id: str,
        service: Service,
        pin_provider: PinProvider,
        *,
        pin_timeout: float = pairing.DEFAULT_PIN_TIMEOUT,
    ) -> None:
        """Pair one service of a discovered device and save the credentials."""
        device = self.device(device_id)
        if service not in device.services:
            raise PairingError(SERVICE_NOT_OFFERED)

        async def pin_for_logs() -> str:
            pin = await pin_provider()
            self.redactor.add(pin.strip(), "pin")  # protocol libraries may log it
            return pin

        await pairing.pair(
            device_id,
            service,
            self._backend.pairing(device_id, service),
            pin_for_logs,
            self.bus,
            on_paired=self._backend.save,
            pin_timeout=pin_timeout,
        )
        # Ask the backend for the new state rather than guessing: a protocol library may store
        # credentials for more than the one service.
        refreshed = await self._backend.describe(device_id)
        if refreshed is None:
            current = self.registry.get(device_id) or device
            refreshed = dataclasses.replace(
                current,
                paired=current.paired | {service},
                needs_pairing=current.needs_pairing - {service},
            )
        self.registry.upsert(refreshed)

    async def forget(self, device_id: str) -> bool:
        """Disconnect and delete stored credentials for a device."""
        await self.disconnect(device_id)
        removed = await self._backend.forget(device_id)
        if removed:
            await self._backend.save()
            device = self.registry.get(device_id)
            if device is not None:
                self.registry.upsert(
                    dataclasses.replace(
                        device,
                        paired=frozenset[Service](),
                        needs_pairing=device.needs_pairing | device.paired,
                    )
                )
        return removed

    # --- Speakers by address, passwords, the network (lessons from AirParrot) ----------

    async def add_address(self, text: str, *, timeout: float = 4.0) -> list[Device]:
        """Ask one address directly; if a speaker answers, remember the address so every scan
        asks it again. Returns what answered. Raises `AddressError` (INVALID, NOT_LOCAL,
        TOO_MANY, or NO_ANSWER when nothing there speaks AirPlay)."""
        address = normalize(text)
        self.redactor.add(address, "address")
        found = list(await self._backend.scan_hosts([address], timeout))
        if not found:
            raise AddressError(AddressError.NO_ANSWER)
        self.addresses.add(address)
        for device in found:
            self.registry.upsert(device)
        return found

    def remove_address(self, address: str) -> bool:
        """Stop asking an address. Its speakers stay until discovery stops seeing them."""
        return self.addresses.remove(address)

    async def set_password(self, device_id: str, password: str) -> None:
        """Save a speaker's password (Home app "Require Password") and use it from now on."""
        device = self.device(device_id)
        self.redactor.add(password, "password")
        await self._backend.set_password(device_id, password)
        refreshed = await self._backend.describe(device_id)
        if refreshed is None:
            refreshed = dataclasses.replace(device, password_set=True)
        self.registry.upsert(dataclasses.replace(refreshed, stereo_pair=device.stereo_pair))
        session = self._sessions.get(device_id)
        if session is not None:
            session.retry_now()

    def start_network_watch(self) -> None:
        """React to network changes at once (rescan, reconnect). Needs a running loop."""
        if self.network_watch is not None:
            self.network_watch.start(self.network_changed)

    async def network_changed(self) -> None:
        """The PC moved networks or woke up: look again now instead of waiting.

        Discovery scans at once; connections waiting out a backoff retry at once (with the
        backoff reset); speakers the user had on that failed for want of an answer try again.
        """
        if self.discovery.running:
            await self.discovery.rescan()
        for session in list(self._sessions.values()):
            session.retry_now()
        self.outputs.retry_unreachable()
        buttons = self.speaker_buttons
        if buttons is not None and buttons.running:
            await buttons.stop()  # announce again on the new addresses
            await buttons.start(self.speaker_button)

    async def start_speaker_buttons(self) -> None:
        """Listen for speakers' own buttons (see `speaker_buttons`)."""
        if self.speaker_buttons is not None and not self.speaker_buttons.running:
            try:
                await self.speaker_buttons.start(self.speaker_button)
            except OSError as exc:
                _LOGGER.info("Speaker buttons are off (%s)", type(exc).__name__)

    async def speaker_button(self, address: str, press: ButtonPress) -> None:
        """A speaker's button: play, pause and skip go to what's playing (the PC's app, or
        Tandem's player); volume keys change that speaker's volume in Tandem."""
        command = press.command
        if command in _VOLUME_BUTTONS:
            device = next((d for d in self.registry.devices() if d.address == address), None)
            if device is None or not self._audio.streaming(device.id):
                return
            if command is ButtonCommand.VOLUME:
                if press.level is not None:
                    self.outputs.note_volume(device.id, press.level)
                return
            current = self.outputs.prefs.get(device.id).volume
            step = VOLUME_STEP if command is ButtonCommand.VOLUME_UP else -VOLUME_STEP
            await self.outputs.set_volume(device.id, (50.0 if current is None else current) + step)
            return
        if self.audio_source is AudioSource.PLAYER:
            player = self.player
            {
                ButtonCommand.PLAY: player.resume,
                ButtonCommand.PAUSE: player.pause,
                ButtonCommand.PLAY_PAUSE: player.toggle,
                ButtonCommand.NEXT: player.next,
                ButtonCommand.PREVIOUS: player.previous,
                ButtonCommand.STOP: player.pause,
            }[command]()
            return
        playing = self.pc_media.now_playing
        is_playing = playing is not None and playing.state == "playing"
        if command in (ButtonCommand.PLAY, ButtonCommand.PAUSE, ButtonCommand.STOP):
            if (command is ButtonCommand.PLAY) == is_playing:
                return  # already where the button wants it
            command = ButtonCommand.PLAY_PAUSE
        await self.pc_media.command(_PC_BUTTONS[command])

    async def check_network(self) -> net_check.Report:
        """Look for the usual reasons speakers can't be found or reached, on this PC."""
        probe = self._network_probe or net_check.Probe()
        speakers = [d.address for d in self.registry.devices() if d.can_play_audio]
        return await net_check.run(
            probe,
            self.scans,
            speakers=speakers + self.addresses.addresses(),
            refused=self.outputs.refused(),
        )

    def session(self, device_id: str, *, max_attempts: int | None = None) -> ConnectionSession:
        """The device's connection session, created on first use."""
        session = self._sessions.get(device_id)
        if session is None:
            session = ConnectionSession(
                device_id,
                self._backend.connector(device_id),
                self.bus,
                max_attempts=max_attempts,
                sleep=self._sleep,
            )
            self._sessions[device_id] = session
        return session

    async def connect(
        self,
        device_id: str,
        *,
        timeout: float | None = None,
        max_attempts: int | None = None,
    ) -> Link:
        """Connect (and keep reconnecting until `disconnect`). Returns the open link."""
        session = self.session(device_id, max_attempts=max_attempts)
        session.start()
        return await session.wait_connected(timeout)

    async def disconnect(self, device_id: str) -> None:
        session = self._sessions.pop(device_id, None)
        if session is not None:
            with suppress(Exception):
                await session.close()

    def diagnostics(
        self,
        out_dir: Path,
        *,
        log_dir: Path | None = None,
        settings: dict[str, Any] | None = None,
    ) -> Path:
        """Write a redacted diagnostics bundle (devices, connection states, logs)."""
        devices = [
            diagnostics.DeviceSummary(
                device,
                self._sessions[device.id].state if device.id in self._sessions else None,
            )
            for device in self.registry.devices()
        ]
        return diagnostics.write_bundle(
            out_dir, self.redactor, devices=devices, settings=settings, log_dir=log_dir
        )

    # --- System audio (Phase 4) ---------------------------------------------------------

    async def start_audio(
        self,
        device_id: str,
        *,
        volume: float | None = None,
        timeout: float | None = AUDIO_CONNECT_TIMEOUT,
    ) -> None:
        """Connect if needed, then stream the PC's audio to the device until `stop_audio`.
        The stream survives connection drops: it resumes when the device reconnects.

        If this call opened the connection and it never comes up, the connection is closed
        again, so a speaker that can't be reached isn't retried forever in the background."""
        if volume is not None and not 0 <= volume <= 100:
            raise ValueError("volume must be between 0 and 100")
        opened = device_id not in self._sessions
        try:
            await self.connect(device_id, timeout=timeout)
        except BaseException:
            if opened:
                await self.disconnect(device_id)
            raise
        self._audio.start(device_id, volume=volume)

    async def stop_audio(self, device_id: str) -> None:
        await self._audio.stop(device_id)

    def audio_stats(self, device_id: str) -> AudioStats | None:
        return self._audio.stats(device_id)

    def streaming_audio(self, device_id: str) -> bool:
        return self._audio.streaming(device_id)

    # --- Outputs and sources (Phases 5 and 6) -------------------------------------------

    def local_outputs(self) -> list[LocalOutput]:
        """The PC's sound outputs that can be used now. While the source is the PC's own audio,
        the default output is left out: playing to it would feed the sound back in."""
        outputs = list(self._backend.local_outputs())
        if self.audio_source is AudioSource.SYSTEM:
            outputs = [o for o in outputs if not o.default]
        return outputs

    def direct_output(self) -> LocalOutput | None:
        """While the source is the PC's own audio, Windows' default output: Windows plays
        there itself (Tandem captures it), so it is always on and Tandem doesn't send to it."""
        if self.audio_source is not AudioSource.SYSTEM:
            return None
        return next((o for o in self._backend.local_outputs() if o.default), None)

    def outputs_on(self) -> dict[str, tuple[StreamState, float | None, int]]:
        """Every output that is on: its stream state, volume and extra delay (ms)."""
        return self._audio.active()

    async def start_output(
        self, output_id: str, *, volume: float | None = None, delay_ms: int = 0
    ) -> None:
        """Turn an output on: an AirPlay device (connecting it if needed) or a PC output."""
        if is_local(output_id):
            if output_id not in {o.id for o in self.local_outputs()}:
                raise AudioError("that sound output isn't available")
            self._audio.start(output_id, volume=volume, delay_ms=delay_ms)
            return
        await self.start_audio(output_id, volume=volume, timeout=self.audio_connect_timeout)
        if delay_ms:
            self._audio.set_delay(output_id, delay_ms)

    async def stop_output(self, output_id: str) -> None:
        await self._audio.stop(output_id)

    async def set_output_volume(self, output_id: str, level: float) -> None:
        await self._audio.set_volume(output_id, level)

    def note_output_volume(self, output_id: str, level: float) -> None:
        """Record a volume the speaker set itself (nothing is sent to it)."""
        self._audio.note_volume(output_id, level)

    async def measure_lag(self, output_id: str) -> lineup.Measurement:
        """How far behind one playing output is, heard through the microphone (milliseconds
        from sending to hearing, less what was already queued for it)."""
        recorded: list[bytes] = []
        mic = self._backend.microphone()
        # Opening a microphone can take a moment (Windows checks its privacy setting): not on
        # the event loop.
        await asyncio.to_thread(mic.start, recorded.append)
        try:
            await self._sleep(lineup.QUIET_MS / 1000)  # the room's noise floor
            ahead = await self._audio.probe(output_id, lineup.chunks(lineup.beep_pattern(), 20), 20)
            remaining = lineup.LISTEN_SECONDS - lineup.QUIET_MS / 1000 - 1.2
            await self._sleep(max(0.0, remaining))
        finally:
            await asyncio.to_thread(mic.stop)
        result = await asyncio.to_thread(lineup.find_pattern, b"".join(recorded))
        if result.lag_ms is None:
            return result
        return lineup.Measurement(max(0, result.lag_ms - lineup.QUIET_MS - round(ahead)))

    def set_output_delay(self, output_id: str, delay_ms: int) -> None:
        self._audio.set_delay(output_id, delay_ms)

    async def set_audio_source(self, source: AudioSource) -> None:
        """Switch between the PC's own audio and the player; outputs keep streaming."""
        if source is self.audio_source:
            return
        self.audio_source = source
        if source is AudioSource.SYSTEM:
            # The default output would now feed back into the capture: turn it off.
            for output in self._backend.local_outputs():
                if output.default and self._audio.streaming(output.id):
                    await self._audio.stop(output.id)
            self._audio.set_capture(self._backend.capture)
        else:
            self._audio.set_capture(self.player.capture)
        self.outputs.refresh()  # the PC's default output is shown, and muted, only for its audio

    # --- Send media to an Apple TV (Phase 7) --------------------------------------------

    async def play_media(self, device_id: str, location: str, *, timeout: float = 30.0) -> None:
        """Play a link or a file on this PC on the device. Replaces what it was sent before."""
        location = location.strip()
        device = self.device(device_id)
        link = await self.connect(device_id, timeout=timeout)
        sender = self._backend.media_sender(link)
        if sender is None:
            raise MediaError("This device can't play videos or links.", MediaError.NOT_A_TV)
        if is_link(location):
            url = location
        else:
            path = Path(location)
            if not await asyncio.to_thread(path.is_file):
                raise MediaError("That file isn't there any more.", MediaError.FILE_GONE)
            await asyncio.to_thread(check_playable, path)
            if self._media_server is None:
                self._media_server = MediaServer()
            await self._media_server.start()
            host = local_address_towards(device.address)
            url = f"http://{host}:{self._media_server.port}{self._media_server.share(path)}"
        await self._sends.start(device_id, sender, url, title_for(location))

    async def stop_media(self, device_id: str) -> None:
        await self._sends.stop(device_id)

    def sending_media(self, device_id: str) -> bool:
        return self._sends.playing(device_id)
