"""Shared test helpers. All device data here is invented (docs/PRIVACY.md, "Test data")."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from tandem.engine.audio import PcmBuffer
from tandem.engine.control import (
    App,
    Artwork,
    Capability,
    ControlError,
    ControlUpdate,
    KeyAction,
    MediaCommand,
    NowPlaying,
    PowerState,
    RemoteKey,
    VolumeControl,
)
from tandem.engine.models import Device, DeviceKind, Service


def make_device(**overrides: Any) -> Device:
    fields: dict[str, Any] = {
        "id": "AA:BB:CC:00:00:01",
        "name": "Living Room Speaker",
        "address": "192.0.2.10",
        "kind": DeviceKind.HOMEPOD,
        "model": "HomePod mini",
        "services": frozenset({Service.AIRPLAY, Service.RAOP}),
    }
    fields.update(overrides)
    return Device(**fields)


class ManualSleep:
    """Stand-in for asyncio.sleep: records each delay and waits until the test releases it."""

    def __init__(self) -> None:
        self.delays: list[float] = []
        self._waiting: list[asyncio.Future[None]] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._waiting.append(future)
        await future

    def release(self) -> None:
        waiting, self._waiting = self._waiting, []
        for future in waiting:
            if not future.done():
                future.set_result(None)

    async def until(self, count: int) -> None:
        """Let the loop run until `count` sleeps have started."""
        for _ in range(1000):
            if len(self.delays) >= count:
                return
            await asyncio.sleep(0)
        raise AssertionError(f"expected {count} sleeps, saw {len(self.delays)}")


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def manual_sleep() -> ManualSleep:
    return ManualSleep()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def tandem_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "tandem-home"
    monkeypatch.setenv("TANDEM_HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def _reset_tandem_logging() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    yield
    for name in ("tandem", "pyatv"):
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        logger.propagate = True
        logger.setLevel(logging.NOTSET)


class FakeLink:
    def __init__(self) -> None:
        self.closed = False
        self.device_id = ""

    async def close(self) -> None:
        self.closed = True


class FakePairingHandle:
    """Accepts `accept_pin`; with `provides_pin=False` it pairs without asking for one."""

    def __init__(
        self,
        *,
        provides_pin: bool = True,
        accept_pin: str = "1234",
        fail_begin: Exception | None = None,
    ) -> None:
        self.provides_pin = provides_pin
        self.accept_pin = accept_pin
        self.fail_begin = fail_begin
        self.entered: str | None = None
        self.finished = False
        self.closed = False

    @property
    def device_provides_pin(self) -> bool:
        return self.provides_pin

    @property
    def has_paired(self) -> bool:
        return self.finished and (not self.provides_pin or self.entered == self.accept_pin)

    async def begin(self) -> None:
        if self.fail_begin is not None:
            raise self.fail_begin

    def pin(self, pin: str) -> None:
        self.entered = pin

    async def finish(self) -> None:
        self.finished = True

    async def close(self) -> None:
        self.closed = True


class FakeBackend:
    """In-memory Backend for engine and CLI tests."""

    def __init__(self, devices: Sequence[Device] = ()) -> None:
        self.devices = list(devices)
        self.loaded = False
        self.saves = 0
        self.credentials: set[tuple[str, Service]] = set()
        self.handles: list[FakePairingHandle] = []
        self.handle_options: dict[str, Any] = {}
        self.connect_failures: dict[str, list[BaseException]] = {}
        self.links: dict[str, list[FakeLink]] = {}
        self.lost_callbacks: dict[str, Callable[[BaseException | None], None]] = {}
        self.describe_enabled = True
        self.controllers: dict[str, FakeController] = {}
        self.sinks: dict[str, list[FakeSink]] = {}
        self.sink_failures: dict[str, list[BaseException]] = {}
        self.captures: list[FakeCapture] = []
        self.audio_enabled = True
        self.controller_options: dict[str, Any] = {}

    async def load(self) -> None:
        self.loaded = True

    async def save(self) -> None:
        self.saves += 1

    async def scan(self, timeout: float) -> Sequence[Device]:
        return list(self.devices)

    async def describe(self, device_id: str) -> Device | None:
        if not self.describe_enabled:
            return None
        for device in self.devices:
            if device.id == device_id:
                paired = frozenset(s for i, s in self.credentials if i == device_id)
                # Some backends store one pairing for several services; this fake's AirPlay
                # pairing also covers MRP, to exercise that.
                if Service.AIRPLAY in paired:
                    paired |= {Service.MRP} & device.services
                return dataclasses.replace(
                    device, paired=paired, needs_pairing=device.needs_pairing - paired
                )
        return None

    def pairing(self, device_id: str, service: Service) -> Callable[[], Awaitable[Any]]:
        async def start() -> FakePairingHandle:
            handle = FakePairingHandle(**self.handle_options)
            self.handles.append(handle)
            original_finish = handle.finish

            async def finish() -> None:
                await original_finish()
                if handle.has_paired:
                    self.credentials.add((device_id, service))

            handle.finish = finish  # type: ignore[method-assign]
            return handle

        return start

    def connector(self, device_id: str) -> Callable[..., Awaitable[FakeLink]]:
        async def connect(on_lost: Callable[[BaseException | None], None]) -> FakeLink:
            failures = self.connect_failures.get(device_id, [])
            if failures:
                raise failures.pop(0)
            link = FakeLink()
            link.device_id = device_id
            self.links.setdefault(device_id, []).append(link)
            self.lost_callbacks[device_id] = on_lost
            return link

        return connect

    async def forget(self, device_id: str) -> bool:
        before = len(self.credentials)
        self.credentials = {c for c in self.credentials if c[0] != device_id}
        return len(self.credentials) != before

    def controller(self, link: Any) -> FakeController | None:
        if not isinstance(link, FakeLink):
            return None
        controller = FakeController(**self.controller_options)
        self.controllers[link.device_id] = controller
        return controller

    def audio_sink(self, link: Any) -> FakeSink | None:
        if not self.audio_enabled or not isinstance(link, FakeLink):
            return None
        failures = self.sink_failures.get(link.device_id, [])
        sink = FakeSink(failures.pop(0) if failures else None)
        self.sinks.setdefault(link.device_id, []).append(sink)
        return sink

    def capture(self) -> FakeCapture:
        capture = FakeCapture()
        self.captures.append(capture)
        return capture


ALL_CAPABILITIES = frozenset(Capability)


class FakeController:
    """Records every command; `push` sends an update as the device would."""

    def __init__(
        self,
        *,
        capabilities: frozenset[Capability] = ALL_CAPABILITIES,
        volume_control: VolumeControl = VolumeControl.LEVEL,
        volume: float | None = 40.0,
        power: PowerState = PowerState.ON,
        now_playing: NowPlaying | None = None,
        fail: ControlError | None = None,
    ) -> None:
        self.caps = capabilities
        self.vol_control = volume_control
        self.level = volume
        self.power_state = power
        self.playing = now_playing or NowPlaying()
        self.fail = fail
        self.calls: list[tuple[Any, ...]] = []
        self.on_update: Callable[[ControlUpdate], None] | None = None
        self.stopped = False
        self.apps_list = [App("com.example.video", "Example Video")]

    def capabilities(self) -> frozenset[Capability]:
        return self.caps

    def volume_control(self) -> VolumeControl:
        return self.vol_control

    def volume(self) -> float | None:
        return self.level if self.vol_control is VolumeControl.LEVEL else None

    def power(self) -> PowerState:
        return self.power_state

    async def _record(self, *call: Any) -> None:
        if self.fail is not None:
            raise self.fail
        self.calls.append(call)

    async def press(self, key: RemoteKey, action: KeyAction) -> None:
        await self._record("press", key, action)

    async def media(self, command: MediaCommand) -> None:
        await self._record("media", command)

    async def seek(self, position: float) -> None:
        await self._record("seek", position)

    async def set_volume(self, level: float) -> None:
        await self._record("set_volume", level)

    async def volume_step(self, up: bool) -> None:
        await self._record("volume_step", up)

    async def set_power(self, on: bool) -> None:
        await self._record("set_power", on)

    async def now_playing(self) -> NowPlaying:
        if self.fail is not None:
            raise self.fail
        return self.playing

    async def artwork(self, width: int | None, height: int | None) -> Artwork | None:
        await self._record("artwork", width, height)
        return Artwork(b"PNG", "image/png", width or 1, height or 1)

    async def apps(self) -> list[App]:
        await self._record("apps")
        return list(self.apps_list)

    async def launch(self, app_id: str) -> None:
        await self._record("launch", app_id)

    async def set_text(self, text: str) -> None:
        await self._record("set_text", text)

    def start(self, on_update: Callable[[ControlUpdate], None]) -> None:
        self.on_update = on_update

    def stop(self) -> None:
        self.stopped = True

    def push(self, update: ControlUpdate) -> None:
        assert self.on_update is not None
        self.on_update(update)


class FakeCapture:
    def __init__(self) -> None:
        self.on_pcm: Callable[[bytes], None] | None = None
        self.stopped = False

    def start(self, on_pcm: Callable[[bytes], None]) -> None:
        self.on_pcm = on_pcm

    def stop(self) -> None:
        self.stopped = True

    def feed(self, data: bytes) -> None:
        assert self.on_pcm is not None
        self.on_pcm(data)


class FakeSink:
    """Reads packets as a sender would (without real-time pacing) until told to fail."""

    def __init__(self, fail: BaseException | None = None) -> None:
        self.fail = fail
        self.volumes: list[float] = []
        self.received = bytearray()
        self.playing = asyncio.Event()
        self.buffer: PcmBuffer | None = None
        self.titles: list[tuple[str, str]] = []

    async def set_volume(self, level: float) -> None:
        self.volumes.append(level)

    async def play(self, buffer: PcmBuffer, *, title: str, artist: str) -> None:
        self.buffer = buffer
        self.titles.append((title, artist))
        self.playing.set()
        if self.fail is not None:
            raise self.fail
        while True:
            data = await buffer.read(352)
            if not data:
                return
            self.received += data
            await asyncio.sleep(0)
