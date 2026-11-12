"""pyatv-backed engine backend: scan, pair, connect and forget (ADR-0001)."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Sequence
from dataclasses import replace

import pyatv
from pyatv.const import DeviceModel, FeatureName, FeatureState, PairingRequirement, Protocol
from pyatv.interface import AppleTV, BaseConfig, DeviceListener, PairingHandler
from pyatv.storage import AbstractStorage

from tandem.engine.adapters import decoders, local_audio
from tandem.engine.adapters.media_sessions import media_sessions as windows_media_sessions
from tandem.engine.adapters.process_loopback import CaptureMode, SystemCapture
from tandem.engine.adapters.pyatv_audio import PyatvAudioSink
from tandem.engine.adapters.pyatv_control import PyatvController
from tandem.engine.adapters.pyatv_ptp import PtpClockShare
from tandem.engine.audio import AudioSink, PcmCapture
from tandem.engine.control import Controller
from tandem.engine.media_send import MediaSender
from tandem.engine.models import Device, DeviceKind, LocalOutput, Service
from tandem.engine.pairing import PairingFactory, PairingHandle
from tandem.engine.pc_media import MediaSessions
from tandem.engine.pc_mute import SpeakerMute
from tandem.engine.player import DecodedStream, Track
from tandem.engine.service import UnknownDeviceError
from tandem.engine.session import Connector, Link, LostCallback

_AUDIO_PROTOCOLS = {Protocol.RAOP, Protocol.AirPlay}
"""The services a speaker's password protects."""

_SERVICES = {
    Protocol.AirPlay: Service.AIRPLAY,
    Protocol.RAOP: Service.RAOP,
    Protocol.Companion: Service.COMPANION,
    Protocol.MRP: Service.MRP,
    Protocol.DMAP: Service.DMAP,
}
_PROTOCOLS = {service: protocol for protocol, service in _SERVICES.items()}

_APPLE_TV_MODELS = {
    DeviceModel.AppleTVGen1,
    DeviceModel.Gen2,
    DeviceModel.Gen3,
    DeviceModel.Gen4,
    DeviceModel.Gen4K,
    DeviceModel.AppleTV4KGen2,
    DeviceModel.AppleTV4KGen3,
}
_HOMEPOD_MODELS = {DeviceModel.HomePod, DeviceModel.HomePodGen2, DeviceModel.HomePodMini}

# Scan time when looking for one device that isn't in the cache.
_LOOKUP_TIMEOUT = 5


def device_kind(model: DeviceModel, services: frozenset[Service]) -> DeviceKind:
    if model in _APPLE_TV_MODELS:
        return DeviceKind.APPLE_TV
    if model in _HOMEPOD_MODELS:
        return DeviceKind.HOMEPOD
    if Service.RAOP in services or Service.AIRPLAY in services:
        return DeviceKind.RECEIVER
    return DeviceKind.OTHER


def device_from_config(config: BaseConfig) -> Device | None:
    """Convert a pyatv scan result, or return None if it has no identifier."""
    identifier = config.identifier
    if not identifier:
        return None
    known = [s for s in config.services if s.protocol in _SERVICES]
    services = frozenset(_SERVICES[s.protocol] for s in known)
    paired = frozenset(_SERVICES[s.protocol] for s in known if s.credentials)
    needs_pairing = frozenset(
        _SERVICES[s.protocol]
        for s in known
        if s.pairing == PairingRequirement.Mandatory and not s.credentials
    )
    info = config.device_info
    audio = [s for s in known if s.protocol in _AUDIO_PROTOCOLS]
    return Device(
        id=identifier,
        name=config.name,
        address=str(config.address),
        kind=device_kind(info.model, services),
        model=info.model_str,
        services=services,
        paired=paired,
        needs_pairing=needs_pairing,
        os_version=info.version or "",
        password_required=any(s.requires_password for s in audio),
        password_set=any(bool(s.password) for s in audio),
    )


def sync_group(config: BaseConfig) -> str | None:
    """The tight-sync group a HomePod announces (`tsid`). Two HomePods sharing one are a stereo
    pair. An identifier: compared only, never logged or shown."""
    service = config.get_service(Protocol.AirPlay)
    if service is None:
        return None
    return service.properties.get("tsid") or None


def mark_stereo_pairs(devices: list[Device], configs: dict[str, BaseConfig]) -> list[Device]:
    """Flag HomePods that share a sync group with another HomePod (a stereo pair).

    Unverified on hardware: the reference HomePods aren't paired. A false flag only changes
    the words shown when the speaker fails to play.
    """
    groups: dict[str, list[str]] = {}
    for device in devices:
        config = configs.get(device.id)
        group = None if config is None else sync_group(config)
        if device.kind is DeviceKind.HOMEPOD and group:
            groups.setdefault(group, []).append(device.id)
    paired = {i for members in groups.values() if len(members) > 1 for i in members}
    return [replace(d, stereo_pair=True) if d.id in paired else d for d in devices]


class _Listener(DeviceListener):
    def __init__(self, on_lost: LostCallback) -> None:
        self._on_lost = on_lost

    def connection_lost(self, exception: Exception) -> None:
        self._on_lost(exception)

    def connection_closed(self) -> None:
        self._on_lost(None)


class PyatvLink:
    """An open pyatv connection. `atv` is the pyatv facade for protocol adapters to use."""

    def __init__(self, atv: AppleTV, listener: _Listener, config: BaseConfig | None = None) -> None:
        self.atv = atv
        self.config = config
        self._listener = listener  # pyatv keeps listeners as weak references

    async def close(self) -> None:
        pending: set[asyncio.Task[object]] = self.atv.close()  # pyright: ignore[reportUnknownVariableType]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


class _PyatvPairing:
    """Adapts pyatv's PairingHandler to the engine's PairingHandle."""

    def __init__(self, handler: PairingHandler) -> None:
        self._handler = handler

    @property
    def device_provides_pin(self) -> bool:
        return self._handler.device_provides_pin

    @property
    def has_paired(self) -> bool:
        return self._handler.has_paired

    async def begin(self) -> None:
        await self._handler.begin()

    def pin(self, pin: str) -> None:
        self._handler.pin(int(pin))  # pyatv zero-pads back to four digits

    async def finish(self) -> None:
        await self._handler.finish()

    async def close(self) -> None:
        await self._handler.close()


class PyatvBackend:
    """Engine backend on pyatv. Credentials live in `storage` (the encrypted vault)."""

    def __init__(self, storage: AbstractStorage, *, ptp_timing: bool = True) -> None:
        self._storage = storage
        self._configs: dict[str, BaseConfig] = {}
        # One PTP clock for every AirPlay 2 stream (ADR-0022), and the receivers that
        # wouldn't take it this run.
        self._ptp = PtpClockShare() if ptp_timing else None
        self._ptp_refused: set[str] = set()
        self._capture_mode = CaptureMode()

    async def load(self) -> None:
        await self._storage.load()

    async def save(self) -> None:
        await self._storage.save()

    async def scan(self, timeout: float) -> Sequence[Device]:
        configs = await pyatv.scan(
            asyncio.get_running_loop(), timeout=max(1, round(timeout)), storage=self._storage
        )
        return self._found(configs)

    async def scan_hosts(self, hosts: Sequence[str], timeout: float) -> Sequence[Device]:
        """Ask these addresses directly (unicast), for networks that block discovery."""
        if not hosts:
            return []
        configs = await pyatv.scan(
            asyncio.get_running_loop(),
            timeout=max(1, round(timeout)),
            hosts=list(hosts),
            storage=self._storage,
        )
        return self._found(configs)

    def _found(self, configs: Sequence[BaseConfig]) -> list[Device]:
        devices: list[Device] = []
        found: dict[str, BaseConfig] = {}
        for config in configs:
            device = device_from_config(config)
            if device is not None:
                self._configs[device.id] = config
                found[device.id] = config
                devices.append(device)
        return mark_stereo_pairs(devices, found)

    async def set_password(self, device_id: str, password: str) -> None:
        """Save the speaker's password (in the encrypted vault) for its audio services."""
        config = await self._config(device_id)
        for service in config.services:
            if service.protocol in _AUDIO_PROTOCOLS:
                service.password = password
        await self._storage.update_settings(config)
        await self._storage.save()

    async def describe(self, device_id: str) -> Device | None:
        config = self._configs.get(device_id)
        if config is None:
            return None
        current = copy.deepcopy(config)
        current.apply(await self._storage.get_settings(current))
        return device_from_config(current)

    async def _config(self, device_id: str) -> BaseConfig:
        config = self._configs.get(device_id)
        if config is not None:
            return config
        found = await pyatv.scan(
            asyncio.get_running_loop(),
            timeout=_LOOKUP_TIMEOUT,
            identifier=device_id,
            storage=self._storage,
        )
        if not found:
            raise UnknownDeviceError(device_id)
        self._configs[device_id] = found[0]
        return found[0]

    def pairing(self, device_id: str, service: Service) -> PairingFactory:
        async def start() -> PairingHandle:
            config = await self._config(device_id)
            handler = await pyatv.pair(
                config, _PROTOCOLS[service], asyncio.get_running_loop(), storage=self._storage
            )
            return _PyatvPairing(handler)

        return start

    def connector(self, device_id: str) -> Connector:
        async def connect(on_lost: LostCallback) -> Link:
            config = await self._config(device_id)
            atv = await pyatv.connect(config, asyncio.get_running_loop(), storage=self._storage)
            listener = _Listener(on_lost)
            atv.listener = listener
            return PyatvLink(atv, listener, config)

        return connect

    async def forget(self, device_id: str) -> bool:
        removed = False
        for settings in list(self._storage.settings):
            protocols = settings.protocols
            identifiers = {
                protocols.airplay.identifier,
                protocols.companion.identifier,
                protocols.dmap.identifier,
                protocols.mrp.identifier,
                protocols.raop.identifier,
            }
            if device_id in identifiers:
                removed = await self._storage.remove_settings(settings) or removed
        self._configs.pop(device_id, None)  # cached services still carry the old credentials
        return removed

    def controller(self, link: Link) -> Controller | None:
        if isinstance(link, PyatvLink):
            return PyatvController(link.atv)
        return None

    def audio_sink(self, link: Link) -> AudioSink | None:
        if isinstance(link, PyatvLink):
            config = link.config
            raop = config.get_service(Protocol.RAOP) if config is not None else None
            return PyatvAudioSink(
                link.atv,
                address=str(config.address) if config is not None else None,
                properties=dict(raop.properties) if raop is not None else None,
                ptp=self._ptp,
                ptp_refused=self._ptp_refused,
            )
        return None

    def capture(self) -> PcmCapture:
        return SystemCapture(self._capture_mode)

    def speaker_mute(self) -> SpeakerMute | None:
        if not self._capture_mode.process:
            return None  # classic loopback follows the mute: muting would silence AirPlay
        from tandem.engine.adapters.endpoint_mute import WindowsSpeakerMute

        return WindowsSpeakerMute(lambda: self._capture_mode.process)

    def microphone(self) -> PcmCapture:  # pragma: no cover - needs a microphone
        from tandem.engine.adapters.microphone import MicrophoneCapture

        return MicrophoneCapture()

    def local_outputs(self) -> Sequence[LocalOutput]:  # pragma: no cover - sound hardware
        return local_audio.list_outputs()

    def local_sink(self, output_id: str) -> AudioSink | None:  # pragma: no cover
        return local_audio.LocalPlaybackSink(output_id)

    def media_sender(self, link: Link) -> MediaSender | None:
        if isinstance(link, PyatvLink) and link.atv.features.in_state(
            FeatureState.Available, FeatureName.PlayUrl
        ):
            return PyatvMediaSender(link.atv)
        return None

    def open_track(self, track: Track) -> DecodedStream:  # pragma: no cover - real files
        return decoders.open_track(track)

    def media_sessions(self) -> MediaSessions:  # pragma: no cover - depends on the PC
        return windows_media_sessions()


class PyatvMediaSender:
    """AirPlay's "play this URL" (Phase 7). pyatv returns once playback has finished."""

    def __init__(self, atv: AppleTV) -> None:
        self._atv = atv

    async def play_url(self, url: str) -> None:
        await self._atv.stream.play_url(url)
