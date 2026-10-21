from __future__ import annotations

import asyncio
from ipaddress import IPv4Address
from typing import Any

import pytest
from pyatv import conf
from pyatv.const import DeviceModel, PairingRequirement, Protocol
from pyatv.interface import DeviceInfo
from pyatv.storage.memory_storage import MemoryStorage

from tandem.engine.adapters import pyatv_adapter
from tandem.engine.adapters.pyatv_adapter import PyatvBackend
from tandem.engine.models import DeviceKind, Service
from tandem.engine.service import UnknownDeviceError

ID = "AA:BB:CC:00:00:01"


def _config(
    name: str = "Living Room Speaker",
    model: DeviceModel = DeviceModel.HomePodMini,
    protocols: tuple[Protocol, ...] = (Protocol.AirPlay, Protocol.RAOP),
    identifier: str | None = ID,
    pairing: PairingRequirement = PairingRequirement.NotNeeded,
    credentials: str | None = None,
) -> conf.AppleTV:
    config = conf.AppleTV(
        IPv4Address("192.0.2.10"), name, device_info=DeviceInfo({DeviceInfo.MODEL: model})
    )
    for port, protocol in enumerate(protocols, start=7000):
        config.add_service(
            conf.ManualService(
                identifier,
                protocol,
                port,
                {},
                credentials=credentials,
                pairing_requirement=pairing,
            )
        )
    return config


def test_device_from_config() -> None:
    device = pyatv_adapter.device_from_config(_config())
    assert device is not None
    assert device.id == ID
    assert device.name == "Living Room Speaker"
    assert device.address == "192.0.2.10"
    assert device.kind is DeviceKind.HOMEPOD
    assert device.model == "HomePod Mini"
    assert device.services == frozenset({Service.AIRPLAY, Service.RAOP})
    assert device.paired == frozenset()
    assert device.needs_pairing == frozenset()
    assert device.can_play_audio
    assert not device.can_remote_control


def test_pairing_status() -> None:
    needs = pyatv_adapter.device_from_config(
        _config(protocols=(Protocol.Companion,), pairing=PairingRequirement.Mandatory)
    )
    assert needs is not None
    assert needs.needs_pairing == {Service.COMPANION}
    paired = pyatv_adapter.device_from_config(
        _config(
            protocols=(Protocol.Companion,),
            pairing=PairingRequirement.Mandatory,
            credentials="invented-pairing-blob-0001",
        )
    )
    assert paired is not None
    assert paired.paired == {Service.COMPANION}
    assert paired.needs_pairing == frozenset()


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


class _FakeAppleTV:
    def __init__(self) -> None:
        self.listener: Any = None
        self.closed = False

    def close(self) -> set[asyncio.Task[None]]:
        self.closed = True

        async def finish() -> None:
            return None

        return {asyncio.get_running_loop().create_task(finish())}


class _FakeHandler:
    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def device_provides_pin(self) -> bool:
        return True

    @property
    def has_paired(self) -> bool:
        return "finish" in self.calls

    async def begin(self) -> None:
        self.calls.append("begin")

    def pin(self, pin: int) -> None:
        self.calls.append(f"pin:{pin}")

    async def finish(self) -> None:
        self.calls.append("finish")

    async def close(self) -> None:
        self.calls.append("close")


@pytest.fixture
def scans(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake_scan(loop: asyncio.AbstractEventLoop, **kwargs: Any) -> list[conf.AppleTV]:
        calls.append(kwargs)
        if kwargs.get("identifier") not in (None, ID):
            return []
        return [_config(), _config(identifier=None)]

    monkeypatch.setattr(pyatv_adapter.pyatv, "scan", fake_scan)
    return calls


async def test_backend_scan(scans: list[dict[str, Any]]) -> None:
    storage = MemoryStorage()
    backend = PyatvBackend(storage)
    devices = await backend.scan(2.6)
    assert [d.id for d in devices] == [ID]
    assert scans == [{"timeout": 3, "storage": storage}]


async def test_backend_connects_reports_drops_and_closes(
    scans: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    atv = _FakeAppleTV()

    async def fake_connect(config: Any, loop: Any, storage: Any = None) -> _FakeAppleTV:
        return atv

    monkeypatch.setattr(pyatv_adapter.pyatv, "connect", fake_connect)
    backend = PyatvBackend(MemoryStorage())
    lost: list[BaseException | None] = []
    link = await backend.connector(ID)(lost.append)  # not scanned yet: looks the device up
    assert scans[0]["identifier"] == ID
    assert isinstance(link, pyatv_adapter.PyatvLink)
    error = ConnectionResetError()
    atv.listener.connection_lost(error)
    atv.listener.connection_closed()
    assert lost == [error, None]
    await link.close()
    assert atv.closed


async def test_backend_unknown_device(scans: list[dict[str, Any]]) -> None:
    backend = PyatvBackend(MemoryStorage())
    with pytest.raises(UnknownDeviceError):
        await backend.connector("other")(lambda _exc: None)


async def test_backend_pairing_adapts_pyatv(
    scans: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = _FakeHandler()
    seen: dict[str, Any] = {}

    async def fake_pair(config: Any, protocol: Protocol, loop: Any, storage: Any = None) -> Any:
        seen["protocol"] = protocol
        return handler

    monkeypatch.setattr(pyatv_adapter.pyatv, "pair", fake_pair)
    backend = PyatvBackend(MemoryStorage())
    await backend.scan(3)
    handle = await backend.pairing(ID, Service.COMPANION)()
    assert seen["protocol"] is Protocol.Companion
    await handle.begin()
    assert handle.device_provides_pin
    handle.pin("0042")
    await handle.finish()
    assert handle.has_paired
    await handle.close()
    assert handler.calls == ["begin", "pin:42", "finish", "close"]


async def test_backend_forget(scans: list[dict[str, Any]]) -> None:
    storage = MemoryStorage()
    backend = PyatvBackend(storage)
    settings = await storage.get_settings(_config(protocols=(Protocol.Companion,)))
    settings.protocols.companion.credentials = "invented-pairing-blob-0001"
    other = _config(protocols=(Protocol.Companion,), identifier="AA:BB:CC:00:00:09")
    await storage.get_settings(other)
    assert await backend.forget(ID)
    assert len(storage.settings) == 1
    assert not await backend.forget(ID)


async def test_backend_load_and_save_use_storage() -> None:
    class Recording(MemoryStorage):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[str] = []

        async def load(self) -> None:
            self.calls.append("load")

        async def save(self) -> None:
            self.calls.append("save")

    storage = Recording()
    backend = PyatvBackend(storage)
    await backend.load()
    await backend.save()
    assert storage.calls == ["load", "save"]


async def test_backend_describe_applies_stored_credentials(scans: list[dict[str, Any]]) -> None:
    storage = MemoryStorage()
    backend = PyatvBackend(storage)
    assert await backend.describe(ID) is None  # not scanned yet
    await backend.scan(3)
    before = await backend.describe(ID)
    assert before is not None
    assert before.paired == frozenset()
    settings = await storage.get_settings(_config())
    settings.protocols.airplay.credentials = "invented-pairing-blob-0001"
    after = await backend.describe(ID)
    assert after is not None
    assert after.paired == {Service.AIRPLAY}
