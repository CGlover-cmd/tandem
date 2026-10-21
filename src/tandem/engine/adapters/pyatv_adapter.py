"""pyatv-backed discovery scanner and session connector (ADR-0001)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pyatv
from pyatv.const import DeviceModel, Protocol
from pyatv.interface import AppleTV, BaseConfig, DeviceListener, Storage

from tandem.engine.discovery import Scanner
from tandem.engine.models import Device, DeviceKind, Service
from tandem.engine.session import Connector, Link, LostCallback

_SERVICES = {
    Protocol.AirPlay: Service.AIRPLAY,
    Protocol.RAOP: Service.RAOP,
    Protocol.Companion: Service.COMPANION,
    Protocol.MRP: Service.MRP,
    Protocol.DMAP: Service.DMAP,
}

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
    services = frozenset(
        _SERVICES[service.protocol] for service in config.services if service.protocol in _SERVICES
    )
    info = config.device_info
    return Device(
        id=identifier,
        name=config.name,
        address=str(config.address),
        kind=device_kind(info.model, services),
        model=info.model_str,
        services=services,
    )


def scanner(storage: Storage | None = None) -> Scanner:
    """A discovery scanner backed by pyatv's mDNS scan."""

    async def scan(timeout: float) -> Sequence[Device]:
        loop = asyncio.get_running_loop()
        configs = await pyatv.scan(loop, timeout=max(1, round(timeout)), storage=storage)
        devices = (device_from_config(config) for config in configs)
        return [device for device in devices if device is not None]

    return scan


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


def connector(config: BaseConfig, storage: Storage | None = None) -> Connector:
    """A session connector that opens a pyatv connection to `config`."""

    async def connect(on_lost: LostCallback) -> Link:
        atv = await pyatv.connect(config, asyncio.get_running_loop(), storage=storage)
        listener = _Listener(on_lost)
        atv.listener = listener
        return PyatvLink(atv, listener)

    return connect
