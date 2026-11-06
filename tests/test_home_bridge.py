"""Tandem as a Home app bridge (Phase 10b). Devices are invented (docs/PRIVACY.md)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from conftest import FakeBackend, ManualSleep, make_device
from tandem import bridge
from tandem.engine.command_dispatch import EngineCommandServices
from tandem.engine.events import EventBus
from tandem.engine.home_bridge import SWITCHES, HomeBridge, HomeChanged, SwitchSpec
from tandem.engine.models import DeviceKind, Service
from tandem.engine.player import PlayerState, TrackKind
from tandem.engine.service import AudioSource, Engine
from tandem.engine.settings import SettingsStore
from tandem.ui import backend as ui


class FakeServer:
    def __init__(self, fail: BaseException | None = None) -> None:
        self.fail = fail
        self.states: dict[str, bool] = {}
        self.on_set: Callable[[str, bool], None] | None = None
        self.stopped = False
        self.is_paired = False

    @property
    def paired(self) -> bool:
        return self.is_paired

    async def start(
        self, switches: Sequence[SwitchSpec], on_set: Callable[[str, bool], None]
    ) -> str:
        if self.fail is not None:
            raise self.fail
        self.on_set = on_set
        return "123-45-678"

    async def stop(self) -> None:
        self.stopped = True

    def set_state(self, switch_id: str, on: bool) -> None:
        self.states[switch_id] = on


class FakeActions:
    def __init__(self) -> None:
        self.on: dict[str, bool] = {"audio": False, "music": False, "tv": False}
        self.fail = False

    def switch_states(self) -> dict[str, bool]:
        return dict(self.on)

    async def set_switch(self, switch_id: str, on: bool) -> None:
        if self.fail:
            raise OSError("no route")
        self.on[switch_id] = on


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


async def test_bridge_starts_shows_code_and_follows_switches() -> None:
    bus = EventBus()
    seen: list[HomeChanged] = []
    bus.subscribe(HomeChanged, seen.append)
    server = FakeServer()
    actions = FakeActions()
    home = HomeBridge(bus, lambda: server, actions)
    assert not home.status().running
    await home.start()
    await home.start()  # once
    status = home.status()
    assert (status.running, status.paired, status.setup_code) == (True, False, "123-45-678")
    assert [s[0] for s in status.switches] == [s.id for s in SWITCHES]
    assert server.states == {"audio": False, "music": False, "tv": False}

    assert server.on_set is not None
    server.on_set("audio", True)  # the Home app flips it
    await _settle()
    assert actions.on["audio"]
    server.is_paired = True
    assert home.status().setup_code is None  # hidden once added

    await home.set_switch("music", True)  # from the command bar
    assert server.states["music"] is True
    actions.fail = True
    server.on_set("tv", True)
    await _settle()  # a failed action is logged, not raised
    await home.stop()
    assert server.stopped
    assert seen[-1].status == home.status()


async def test_a_bridge_that_wont_start_says_so() -> None:
    home = HomeBridge(EventBus(), lambda: FakeServer(OSError("port busy")), FakeActions())
    await home.start()
    status = home.status()
    assert status.enabled
    assert not status.running
    assert status.error == "OSError"
    home.refresh()  # nothing to update: no server


TV = make_device(
    id="AA:BB:CC:00:00:02",
    name="Living Room TV",
    kind=DeviceKind.APPLE_TV,
    services=frozenset({Service.AIRPLAY, Service.COMPANION}),
    paired=frozenset({Service.COMPANION}),
)
SPEAKER = make_device()


@pytest.fixture
async def backend(tmp_path: Path, manual_sleep: ManualSleep) -> bridge.EngineBackend:
    fake = FakeBackend([TV, SPEAKER])
    fake.tracks["C:/Music/a.mp3"] = bytes(4 * 441)
    bus = EventBus()
    engine = Engine(fake, bus=bus, sleep=manual_sleep, discovery_interval=60.0)
    server = FakeServer()
    backend = bridge.EngineBackend(
        engine, SettingsStore(tmp_path / "settings.json", bus), home_server=lambda: server
    )
    await backend.start()
    backend._fake = fake  # pyright: ignore[reportAttributeAccessIssue]
    return backend


async def test_home_bridge_on_the_engine(backend: bridge.EngineBackend) -> None:
    assert not backend.home().enabled
    await backend.set_home_bridge(True)
    home = backend.home()
    assert home.enabled
    assert home.running
    assert home.setup_code == "123-45-678"

    await backend.set_switch("audio", True)  # nothing used yet: the speakers that need no PIN
    assert SPEAKER.id in backend._engine.outputs_on()  # pyright: ignore[reportPrivateUsage]
    assert backend.switch_states()["audio"]
    await backend.set_switch("audio", False)
    assert not backend.switch_states()["audio"]

    engine = backend._engine  # pyright: ignore[reportPrivateUsage]
    engine.player.add([(TrackKind.FILE, "C:/Music/a.mp3", "A")])
    await backend.set_switch("music", True)
    assert engine.audio_source is AudioSource.PLAYER
    await backend.set_switch("music", False)
    assert engine.player.status.state is not PlayerState.PLAYING

    await backend.set_switch("tv", False)
    assert ("set_power", False) in backend._fake.controllers[TV.id].calls  # pyright: ignore

    services = EngineCommandServices(engine, home=backend.home_bridge)
    assert [s.target.name for s in services.switches()] == [s.name for s in SWITCHES]
    await services.set_switch("audio", True)
    await backend.set_home_bridge(False)
    assert services.switches() == []
    assert not backend.home().running
    await backend.stop()


async def test_without_a_bridge_server(tmp_path: Path) -> None:
    bus = EventBus()
    engine = Engine(FakeBackend(), bus=bus)
    backend = bridge.EngineBackend(engine, SettingsStore(tmp_path / "s.json", bus))
    with pytest.raises(ui.HomeError):
        await backend.set_home_bridge(True)
    assert not backend.home().enabled


async def test_a_failing_bridge_is_reported(tmp_path: Path) -> None:
    bus = EventBus()
    engine = Engine(FakeBackend(), bus=bus)
    backend = bridge.EngineBackend(
        engine,
        SettingsStore(tmp_path / "s.json", bus),
        home_server=lambda: FakeServer(OSError("port busy")),
    )
    with pytest.raises(ui.HomeError, match="couldn't start"):
        await backend.set_home_bridge(True)
    assert backend.home().failed
