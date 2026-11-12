"""Reconnecting at once, stalled streams, passwords, stereo pairs and the media check
(lessons from AirParrot, ADR-0023)."""

from __future__ import annotations

import asyncio
import struct
from ipaddress import IPv4Address
from pathlib import Path
from typing import Any

import pytest
from pyatv import conf
from pyatv.const import DeviceModel, Protocol
from pyatv.interface import DeviceInfo
from pyatv.storage.memory_storage import MemoryStorage

from conftest import FakeBackend, FakeCapture, FakeClock, ManualSleep, make_device
from tandem.engine.adapters import pyatv_adapter
from tandem.engine.adapters.pyatv_adapter import PyatvBackend
from tandem.engine.audio import AudioStreamChanged, PcmBuffer, StreamState
from tandem.engine.audio_hub import LOCAL_PREFIX, START_GRACE, AudioHub
from tandem.engine.backoff import Backoff
from tandem.engine.events import EventBus
from tandem.engine.media_send import MediaError, check_playable, mp4_codecs
from tandem.engine.models import DeviceKind
from tandem.engine.outputs import OutputProblem, classify
from tandem.engine.service import Engine
from tandem.engine.session import (
    ConnectionFailedError,
    ConnectionSession,
    ConnectionState,
    LostCallback,
)

LOCKED = make_device(
    id="AA:BB:CC:00:00:51", name="Attic Speaker", address="192.0.2.51", password_required=True
)
NO_JITTER = Backoff(initial=1.0, maximum=8.0, factor=2.0, jitter=0.0)


# --- Connections retry at once when the network changes -----------------------------------


class _Link:
    async def close(self) -> None:
        pass


class _Connector:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0
        self.on_lost: LostCallback | None = None

    async def __call__(self, on_lost: LostCallback) -> _Link:
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise ConnectionRefusedError
        self.on_lost = on_lost
        return _Link()


async def _until(condition: Any) -> None:
    for _ in range(500):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError("timed out")


async def test_retry_now_cuts_the_backoff_short(manual_sleep: ManualSleep) -> None:
    connector = _Connector(failures=1)
    session = ConnectionSession(
        "AA:BB:CC:00:00:52", connector, EventBus(), backoff=NO_JITTER, sleep=manual_sleep
    )
    assert not session.retry_now()  # not waiting: nothing to cut short
    session.start()
    await _until(lambda: session.state is ConnectionState.WAITING)
    assert session.retry_now()
    await session.wait_connected(timeout=1)
    assert connector.calls == 2
    await session.close()


async def test_reconnect_drops_a_connection_that_stalled(manual_sleep: ManualSleep) -> None:
    connector = _Connector(failures=0)
    session = ConnectionSession(
        "AA:BB:CC:00:00:53", connector, EventBus(), backoff=NO_JITTER, sleep=manual_sleep
    )
    assert not session.reconnect()  # not connected
    session.start()
    await session.wait_connected(timeout=1)
    assert session.reconnect()
    await _until(lambda: session.state is ConnectionState.WAITING)
    assert session.retry_now()
    await _until(lambda: connector.calls == 2 and session.state is ConnectionState.CONNECTED)
    await session.close()


async def test_a_stalled_stream_reconnects_its_session() -> None:
    backend = FakeBackend([LOCKED])
    engine = Engine(backend)
    await engine.scan()
    await engine.connect(LOCKED.id, timeout=1)
    session = engine.session(LOCKED.id)
    engine.bus.publish(AudioStreamChanged(LOCKED.id, StreamState.WAITING, "Stalled"))
    await _until(lambda: session.state is not ConnectionState.CONNECTED)
    engine.bus.publish(AudioStreamChanged(LOCAL_PREFIX + "x", StreamState.WAITING, "Stalled"))
    await engine.close()


# --- The stall watchdog ------------------------------------------------------------------------


class _StuckSink:
    """Starts, then never takes another frame (the stream died without an error)."""

    def __init__(self) -> None:
        self.buffer: PcmBuffer | None = None
        self.plays = 0
        self.started = asyncio.Event()

    async def set_volume(self, level: float) -> None:
        pass

    async def play(self, buffer: PcmBuffer, *, title: str, artist: str) -> None:
        self.buffer = buffer
        self.plays += 1
        self.started.set()
        await asyncio.Event().wait()


async def test_a_stream_that_stops_taking_audio_is_restarted() -> None:
    clock = FakeClock()
    sink = _StuckSink()
    bus = EventBus()
    states: list[tuple[StreamState, str | None]] = []
    bus.subscribe(AudioStreamChanged, lambda e: states.append((e.state, e.reason)))
    capture = FakeCapture()
    hub = AudioHub(
        bus,
        lambda: capture,
        lambda _link: None,
        lambda _id: None,
        local_sink=lambda _id: sink,
        clock=clock,
        backoff=Backoff(initial=0.0, maximum=0.0, factor=1.0, jitter=0.0),
    )
    output = LOCAL_PREFIX + "a"
    hub.start(output)
    await sink.started.wait()
    assert hub.check_stalls() == []  # just started
    buffer = sink.buffer
    assert buffer is not None
    buffer.note_timed(352, 0)  # it took some audio
    clock.now += 1
    assert hub.check_stalls() == []
    clock.now += 10  # ...then nothing for 10 s
    assert hub.check_stalls() == [output]
    assert (StreamState.WAITING, "Stalled") in states
    await _until(lambda: sink.plays == 2)  # restarted on its own
    clock.now += START_GRACE + 1  # a fresh start that never takes any audio
    assert hub.check_stalls() == [output]
    await hub.close()


# --- Speaker passwords and stereo pairs -----------------------------------------------------------


def test_classify_names_passwords_and_stereo_pairs() -> None:
    assert classify(None, None, LOCKED) is OutputProblem.PASSWORD
    known = make_device(password_required=True, password_set=True)
    assert classify("AuthenticationError", None, known) is OutputProblem.PASSWORD  # wrong one
    assert classify(None, TimeoutError(), known) is OutputProblem.UNREACHABLE
    paired = make_device(stereo_pair=True)
    assert classify(None, RuntimeError(), paired) is OutputProblem.STEREO_PAIR
    assert classify("AuthenticationError", None, paired) is OutputProblem.ACCESS


async def test_a_saved_password_is_used_from_then_on() -> None:
    backend = FakeBackend([LOCKED])
    engine = Engine(backend)
    await engine.scan()
    await engine.set_password(LOCKED.id, "invented-secret")
    assert backend.passwords == {LOCKED.id: "invented-secret"}
    assert engine.device(LOCKED.id).password_set
    assert "invented-secret" not in engine.redactor.redact("pw invented-secret")
    backend.describe_enabled = False
    await engine.connect(LOCKED.id, timeout=1)
    await engine.set_password(LOCKED.id, "another-secret")  # nothing to describe: kept as set
    assert engine.device(LOCKED.id).password_set
    await engine.close()


def _config(
    identifier: str, model: DeviceModel, tsid: str | None, *, password: bool = False
) -> conf.AppleTV:
    config = conf.AppleTV(
        IPv4Address("192.0.2.10"),
        "Living Room Speaker",
        device_info=DeviceInfo({DeviceInfo.MODEL: model, DeviceInfo.VERSION: "18.1"}),
    )
    airplay: dict[str, str] = {} if tsid is None else {"tsid": tsid}
    config.add_service(conf.ManualService(identifier, Protocol.AirPlay, 7000, airplay))
    # pyatv sets the flag from the "pw" key while it scans.
    config.add_service(
        conf.ManualService(identifier, Protocol.RAOP, 7001, {}, requires_password=password)
    )
    return config


def test_homepods_sharing_a_sync_group_are_a_stereo_pair() -> None:
    left = _config("AA:BB:CC:00:00:61", DeviceModel.HomePodMini, "group-1")
    right = _config("AA:BB:CC:00:00:62", DeviceModel.HomePodMini, "group-1")
    alone = _config("AA:BB:CC:00:00:63", DeviceModel.HomePodMini, "group-2")
    bare = _config("AA:BB:CC:00:00:64", DeviceModel.HomePodMini, None)
    configs = {c.identifier: c for c in (left, right, alone, bare)}
    devices = [d for c in configs.values() if (d := pyatv_adapter.device_from_config(c))]
    marked = {d.id: d.stereo_pair for d in pyatv_adapter.mark_stereo_pairs(devices, configs)}  # type: ignore[arg-type]
    assert marked == {
        "AA:BB:CC:00:00:61": True,
        "AA:BB:CC:00:00:62": True,
        "AA:BB:CC:00:00:63": False,
        "AA:BB:CC:00:00:64": False,
    }
    assert pyatv_adapter.sync_group(conf.AppleTV(IPv4Address("192.0.2.10"), "x")) is None


def test_devices_show_their_software_version_and_password() -> None:
    device = pyatv_adapter.device_from_config(
        _config("AA:BB:CC:00:00:65", DeviceModel.HomePodMini, None, password=True)
    )
    assert device is not None
    assert device.kind is DeviceKind.HOMEPOD
    assert device.os_version == "18.1"
    assert device.password_required
    assert not device.password_set


async def test_the_adapter_asks_addresses_and_saves_passwords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config("AA:BB:CC:00:00:66", DeviceModel.HomePodMini, None, password=True)
    asked: list[list[str]] = []

    async def scan(_loop: object, *, timeout: int, hosts: list[str], storage: object) -> list[Any]:
        asked.append(hosts)
        return [config]

    monkeypatch.setattr(pyatv_adapter.pyatv, "scan", scan)
    backend = PyatvBackend(MemoryStorage())
    assert await backend.scan_hosts([], 3) == []
    (found,) = await backend.scan_hosts(["192.0.2.10"], 3)
    assert asked == [["192.0.2.10"]]
    await backend.set_password(found.id, "invented-secret")
    described = await backend.describe(found.id)
    assert described is not None
    assert described.password_set


# --- What the Apple TV can play ----------------------------------------------------------------


def _box(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", 8 + len(body)) + kind + body


def _mp4(*codecs: bytes) -> bytes:
    entries = b"".join(_box(c, b"\0" * 8) for c in codecs)
    stsd = _box(b"stsd", b"\0\0\0\0" + struct.pack(">I", len(codecs)) + entries)
    track = _box(b"trak", _box(b"mdia", _box(b"minf", _box(b"stbl", stsd))))
    return _box(b"ftyp", b"isom\0\0\0\0") + _box(b"moov", track)


def test_mp4_codecs_reads_the_sample_entries(tmp_path: Path) -> None:
    path = tmp_path / "clip.mp4"
    path.write_bytes(_mp4(b"avc1", b"mp4a"))
    assert mp4_codecs(path) == {b"avc1", b"mp4a"}
    path.write_bytes(b"\0\0\0\x01moov\0\0\0\0\0\0\0\x10" + b"\0" * 8)  # 64-bit size
    assert mp4_codecs(path) == frozenset()
    path.write_bytes(b"\0\0\0\x00free")  # runs to the end of the file
    assert mp4_codecs(path) == frozenset()
    path.write_bytes(b"\0\0\x10\x00moov")  # longer than the file
    assert mp4_codecs(path) == frozenset()


def test_files_the_tv_cannot_play_are_caught_first(tmp_path: Path) -> None:
    good = tmp_path / "good.mp4"
    good.write_bytes(_mp4(b"hvc1", b"mp4a"))
    check_playable(good)
    (tmp_path / "clip.mov").write_bytes(b"not an mp4 at all")
    check_playable(tmp_path / "clip.mov")  # unreadable: the TV has the last word
    for name, data in [("vp9.mp4", _mp4(b"vp09")), ("hev1.m4v", _mp4(b"hev1", b"mp4a"))]:
        path = tmp_path / name
        path.write_bytes(data)
        with pytest.raises(MediaError) as error:
            check_playable(path)
        assert error.value.reason == MediaError.NOT_PLAYABLE, name
    with pytest.raises(MediaError) as wrong_kind:
        check_playable(tmp_path / "film.mkv")
    assert wrong_kind.value.reason == MediaError.NOT_PLAYABLE


class AuthenticationError(Exception):
    """Named like pyatv's."""


async def test_a_refused_password_is_not_retried(manual_sleep: ManualSleep) -> None:
    calls: list[int] = []

    async def refuse(_on_lost: LostCallback) -> _Link:
        calls.append(1)
        raise AuthenticationError

    session = ConnectionSession(
        "AA:BB:CC:00:00:54", refuse, EventBus(), backoff=NO_JITTER, sleep=manual_sleep
    )
    session.start()
    with pytest.raises(ConnectionFailedError):
        await session.wait_connected(timeout=1)
    assert session.state is ConnectionState.FAILED
    assert calls == [1]
    await session.close()
