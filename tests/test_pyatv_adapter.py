from __future__ import annotations

import asyncio
from ipaddress import IPv4Address
from typing import Any

import pytest
from pyatv import conf
from pyatv.const import DeviceModel, Protocol
from pyatv.interface import DeviceInfo

from tandem.engine.adapters import pyatv_adapter
from tandem.engine.models import DeviceKind, Service


def _config(
    name: str = "Living Room Speaker",
    model: DeviceModel = DeviceModel.HomePodMini,
    protocols: tuple[Protocol, ...] = (Protocol.AirPlay, Protocol.RAOP),
    identifier: str | None = "AA:BB:CC:00:00:01",
) -> conf.AppleTV:
    config = conf.AppleTV(
        IPv4Address("192.0.2.10"), name, device_info=DeviceInfo({DeviceInfo.MODEL: model})
    )
    for port, protocol in enumerate(protocols, start=7000):
        config.add_service(conf.ManualService(identifier, protocol, port, {}))
    return config


def test_device_from_config() -> None:
    device = pyatv_adapter.device_from_config(_config())
    assert device is not None
    assert device.id == "AA:BB:CC:00:00:01"
    assert device.name == "Living Room Speaker"
    assert device.address == "192.0.2.10"
    assert device.kind is DeviceKind.HOMEPOD
    assert device.model == "HomePod Mini"
    assert device.services == frozenset({Service.AIRPLAY, Service.RAOP})
    assert device.can_play_audio
    assert not device.can_remote_control


def test_device_without_identifier_is_skipped() -> None:
    assert pyatv_adapter.device_from_config(_config(identifier=None)) is None


@pytest.mark.parametrize(
    ("model", "protocols", "kind"),
    [
        (DeviceModel.AppleTV4KGen2, (Protocol.Companion, Protocol.AirPlay), DeviceKind.APPLE_TV),
        (DeviceModel.HomePod, (Protocol.RAOP,), DeviceKind.HOMEPOD),
        (DeviceModel.Unknown, (Protocol.RAOP,), DeviceKind.RECEIVER),
        (DeviceModel.Unknown, (Protocol.Companion,), DeviceKind.OTHER),
    ],
)
def test_device_kind(model: DeviceModel, protocols: tuple[Protocol, ...], kind: DeviceKind) -> None:
    device = pyatv_adapter.device_from_config(_config(model=model, protocols=protocols))
    assert device is not None
    assert device.kind is kind


async def test_scanner_wraps_pyatv_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_scan(loop: asyncio.AbstractEventLoop, **kwargs: Any) -> list[conf.AppleTV]:
        calls.append(kwargs)
        return [_config(), _config(identifier=None)]

    monkeypatch.setattr(pyatv_adapter.pyatv, "scan", fake_scan)
    devices = await pyatv_adapter.scanner()(2.6)
    assert [d.id for d in devices] == ["AA:BB:CC:00:00:01"]
    assert calls == [{"timeout": 3, "storage": None}]


class _FakeAppleTV:
    def __init__(self) -> None:
        self.listener: Any = None
        self.closed = False

    def close(self) -> set[asyncio.Task[None]]:
        self.closed = True

        async def finish() -> None:
            return None

        return {asyncio.get_running_loop().create_task(finish())}


async def test_connector_reports_drops_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    atv = _FakeAppleTV()

    async def fake_connect(config: Any, loop: Any, storage: Any = None) -> _FakeAppleTV:
        return atv

    monkeypatch.setattr(pyatv_adapter.pyatv, "connect", fake_connect)
    lost: list[BaseException | None] = []
    link = await pyatv_adapter.connector(_config())(lost.append)
    assert isinstance(link, pyatv_adapter.PyatvLink)
    assert link.atv is atv  # pyright: ignore[reportUnnecessaryComparison]
    error = ConnectionResetError()
    atv.listener.connection_lost(error)
    atv.listener.connection_closed()
    assert lost == [error, None]
    await link.close()
    assert atv.closed
