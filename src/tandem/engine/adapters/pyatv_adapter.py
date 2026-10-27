"""pyatv-backed engine backend: scan, pair, connect and forget (ADR-0001)."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Sequence

import pyatv
from pyatv.const import DeviceModel, PairingRequirement, Protocol
from pyatv.interface import AppleTV, BaseConfig, DeviceListener, PairingHandler
from pyatv.storage import AbstractStorage

from tandem.engine.adapters.loopback import LoopbackCapture
from tandem.engine.adapters.pyatv_audio import PyatvAudioSink
from tandem.engine.adapters.pyatv_control import PyatvController
from tandem.engine.audio import AudioSink, PcmCapture
from tandem.engine.control import Controller
from tandem.engine.models import Device, DeviceKind, Service
from tandem.engine.pairing import PairingFactory, PairingHandle
from tandem.engine.service import UnknownDeviceError
from tandem.engine.session import Connector, Link, LostCallback

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
    return Device(
        id=identifier,
        name=config.name,
        address=str(config.address),
        kind=device_kind(info.model, services),
        model=info.model_str,
        services=services,
        paired=paired,
        needs_pairing=needs_pairing,
    )


class _Listener(DeviceListener):
    def __init__(self, on_lost: LostCallback) -> None:
        self._on_lost = on_lost

    def connection_lost(self, exception: Exception) -> None:
        self._on_lost(exception)

    def connection_closed(self) -> None:
        self._on_lost(None)


class PyatvLink:
    """An open pyatv connection. `atv` is the pyatv facade for protocol adapters to use."""

    def __init__(self, atv: AppleTV, listener: _Listener) -> None:
        self.atv = atv
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

    def __init__(self, storage: AbstractStorage) -> None:
        self._storage = storage
        self._configs: dict[str, BaseConfig] = {}

    async def load(self) -> None:
        await self._storage.load()

    async def save(self) -> None:
        await self._storage.save()

    async def scan(self, timeout: float) -> Sequence[Device]:
        configs = await pyatv.scan(
            asyncio.get_running_loop(), timeout=max(1, round(timeout)), storage=self._storage
        )
        devices: list[Device] = []
        for config in configs:
            device = device_from_config(config)
            if device is not None:
                self._configs[device.id] = config
                devices.append(device)
        return devices

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
            return PyatvLink(atv, listener)

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
            return PyatvAudioSink(link.atv)
        return None

    def capture(self) -> PcmCapture:
        return LoopbackCapture()
