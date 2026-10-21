from __future__ import annotations

import asyncio

import pytest

from conftest import FakeBackend, ManualSleep, make_device
from tandem.engine.models import DeviceKind, Service
from tandem.engine.pairing import PairingError
from tandem.engine.service import SERVICE_NOT_OFFERED, Engine, UnknownDeviceError
from tandem.engine.session import ConnectionFailedError, ConnectionState

TV = make_device(
    id="AA:BB:CC:00:00:02",
    name="Den TV",
    kind=DeviceKind.APPLE_TV,
    model="Apple TV 4K (gen 2)",
    services=frozenset({Service.COMPANION, Service.AIRPLAY, Service.RAOP}),
    needs_pairing=frozenset({Service.COMPANION, Service.AIRPLAY}),
)
SPEAKER = make_device()


async def _pin() -> str:
    return "1234"


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend([TV, SPEAKER])


@pytest.fixture
def engine(backend: FakeBackend, manual_sleep: ManualSleep) -> Engine:
    return Engine(backend, sleep=manual_sleep)


async def test_open_loads_credentials(engine: Engine, backend: FakeBackend) -> None:
    await engine.open()
    assert backend.loaded


async def test_scan_lists_devices(engine: Engine) -> None:
    assert {d.id for d in await engine.scan()} == {TV.id, SPEAKER.id}
    assert engine.device(TV.id) == TV


async def test_unknown_device(engine: Engine) -> None:
    with pytest.raises(UnknownDeviceError):
        engine.device("nope")
    with pytest.raises(UnknownDeviceError):
        await engine.pair("nope", Service.COMPANION, _pin)


async def test_pair_saves_and_marks_the_device_paired(engine: Engine, backend: FakeBackend) -> None:
    await engine.scan()
    await engine.pair(TV.id, Service.COMPANION, _pin)
    assert backend.saves == 1
    assert (TV.id, Service.COMPANION) in backend.credentials
    device = engine.device(TV.id)
    assert device.paired == {Service.COMPANION}
    assert device.needs_pairing == {Service.AIRPLAY}


async def test_pin_is_redacted_from_logs(engine: Engine, backend: FakeBackend) -> None:
    await engine.scan()
    backend.handle_options = {"accept_pin": "4821"}

    async def pin() -> str:
        return "4821"

    await engine.pair(TV.id, Service.COMPANION, pin)
    assert engine.redactor.redact("PIN changed to 4821") == "PIN changed to <pin-1>"


async def test_pair_unoffered_service(engine: Engine) -> None:
    await engine.scan()
    with pytest.raises(PairingError) as caught:
        await engine.pair(SPEAKER.id, Service.COMPANION, _pin)
    assert caught.value.reason == SERVICE_NOT_OFFERED


async def test_failed_pairing_saves_nothing(engine: Engine, backend: FakeBackend) -> None:
    await engine.scan()
    backend.handle_options = {"accept_pin": "0000"}
    with pytest.raises(PairingError):
        await engine.pair(TV.id, Service.COMPANION, _pin)
    assert backend.saves == 0
    assert engine.device(TV.id).paired == frozenset()


async def test_forget_removes_credentials(engine: Engine, backend: FakeBackend) -> None:
    await engine.scan()
    await engine.pair(TV.id, Service.COMPANION, _pin)
    await engine.connect(TV.id, timeout=1)
    assert await engine.forget(TV.id)
    assert backend.saves == 2
    assert backend.links[TV.id][0].closed
    device = engine.device(TV.id)
    assert device.paired == frozenset()
    assert device.needs_pairing == {Service.COMPANION, Service.AIRPLAY}
    assert not await engine.forget(TV.id)
    assert backend.saves == 2


async def test_connect_and_disconnect(engine: Engine, backend: FakeBackend) -> None:
    link = await engine.connect(SPEAKER.id, timeout=1)
    assert engine.session(SPEAKER.id).state is ConnectionState.CONNECTED
    await engine.disconnect(SPEAKER.id)
    assert link.closed  # type: ignore[attr-defined]
    await engine.disconnect(SPEAKER.id)  # already disconnected: harmless


async def test_connect_gives_up_after_max_attempts(
    engine: Engine, backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    backend.connect_failures[SPEAKER.id] = [OSError(), OSError()]
    task = asyncio.ensure_future(engine.connect(SPEAKER.id, timeout=1, max_attempts=2))
    await manual_sleep.until(1)
    manual_sleep.release()
    with pytest.raises(ConnectionFailedError):
        await task


async def test_close_disconnects_everything(engine: Engine, backend: FakeBackend) -> None:
    await engine.connect(SPEAKER.id, timeout=1)
    await engine.connect(TV.id, timeout=1)
    engine.discovery.start()
    await engine.close()
    assert all(links[0].closed for links in backend.links.values())
    assert not engine.discovery.running


async def test_pair_without_backend_refresh_still_updates(
    engine: Engine, backend: FakeBackend
) -> None:
    backend.describe_enabled = False
    await engine.scan()
    await engine.pair(TV.id, Service.AIRPLAY, _pin)
    device = engine.device(TV.id)
    assert device.paired == {Service.AIRPLAY}
    assert device.needs_pairing == {Service.COMPANION}
