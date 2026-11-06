"""Tandem's player (Phase 6). Track titles and paths are invented (docs/PRIVACY.md)."""

from __future__ import annotations

import asyncio
import struct
import threading

import pytest

from conftest import FakeBackend, FakeStream
from tandem.engine.events import EventBus
from tandem.engine.player import (
    CHUNK_FRAMES,
    MAX_QUEUE,
    Player,
    PlayerChanged,
    PlayerState,
    Track,
    TrackKind,
)

TONE = struct.pack("<hh", 500, 500) * (CHUNK_FRAMES * 5)


class Clock:
    """Fake time: `sleep` moves it forward instead of waiting."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _player(backend: FakeBackend, bus: EventBus | None = None) -> tuple[Player, Clock]:
    clock = Clock()
    player = Player(
        bus or EventBus(), backend.open_track, clock=clock, sleep=clock.sleep, status_interval=0
    )
    return player, clock


async def _until(predicate: object, *, seconds: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while loop.time() < deadline:
        if callable(predicate) and predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition not reached")


@pytest.fixture
def backend() -> FakeBackend:
    backend = FakeBackend()
    backend.tracks = {"C:/Music/one.mp3": TONE, "C:/Music/two.flac": TONE}
    return backend


async def test_plays_the_queue_in_order_into_the_capture(backend: FakeBackend) -> None:
    bus = EventBus()
    states: list[PlayerState] = []
    bus.subscribe(PlayerChanged, lambda e: states.append(e.status.state))
    player, _ = _player(backend, bus)
    added = player.add(
        [
            (TrackKind.FILE, "C:/Music/one.mp3", "One"),
            (TrackKind.FILE, "C:/Music/two.flac", "Two"),
        ]
    )
    received = bytearray()
    lock = threading.Lock()

    def sink(data: bytes) -> None:
        with lock:
            received.extend(data)

    capture = player.capture()
    capture.start(sink)
    player.play()
    await _until(lambda: player.status.state is PlayerState.STOPPED and len(received) > 0)
    assert len(received) == 2 * len(TONE)
    assert player.status.index == 1
    assert player.status.position == 0.0
    assert PlayerState.LOADING in states
    assert PlayerState.PLAYING in states
    assert [t.title for t in player.status.queue] == ["One", "Two"]
    assert added[0].id != added[1].id
    capture.stop()
    await player.close()


async def test_pause_resume_next_previous(backend: FakeBackend) -> None:
    backend.tracks["slow"] = TONE * 50
    player, _ = _player(backend)
    a, b = player.add([(TrackKind.FILE, "slow", "A"), (TrackKind.FILE, "slow", "B")])
    player.play(a.id)
    await _until(lambda: player.status.state is PlayerState.PLAYING)
    player.pause()
    assert player.status.state is PlayerState.PAUSED
    player.toggle()
    assert player.status.state is PlayerState.PLAYING
    player.next()
    assert player.status.index == 1
    player.previous()  # at the start of B: back to A
    assert player.status.index == 0
    player.next()
    player.next()  # past the end: stops
    assert player.status.state is PlayerState.STOPPED
    player.play()  # plays the current track again
    await _until(lambda: player.status.state is PlayerState.PLAYING)
    assert player.status.current == b
    player.stop()
    assert player.status.state is PlayerState.STOPPED
    await player.close()


async def test_a_track_that_wont_open_is_reported(backend: FakeBackend) -> None:
    player, _ = _player(backend)
    player.add([(TrackKind.RADIO, "http://radio.example/stream", "Example FM")])
    player.play()
    await _until(lambda: player.status.error is not None)
    assert player.status.error == "FileNotFoundError"
    assert player.status.state is PlayerState.STOPPED
    await player.close()


async def test_a_track_that_fails_midway_is_reported(backend: FakeBackend) -> None:
    class Broken(FakeStream):
        def read(self, frames: int) -> bytes:
            raise OSError("stream lost")

    player = Player(EventBus(), lambda track: Broken(b""), sleep=lambda s: None)
    player.add([(TrackKind.RADIO, "http://radio.example/stream", "Example FM")])
    player.play()
    await _until(lambda: player.status.error == "OSError")
    await player.close()


async def test_queue_editing(backend: FakeBackend) -> None:
    player, _ = _player(backend)
    a, b, c = player.add([(TrackKind.FILE, "C:/Music/one.mp3", t) for t in ("A", "B", "C")])
    player.remove("missing")  # ignored
    player.play(c.id)
    player.remove(a.id)
    assert player.status.index == 1  # C moved up
    player.remove(c.id)  # the current track: stops
    assert player.status.index is None
    assert [t.id for t in player.status.queue] == [b.id]
    player.play("missing")  # not in the queue: nothing happens
    player.clear()
    assert player.status.queue == ()
    player.play()  # empty queue: nothing to play
    player.previous()  # nothing current: ignored
    assert player.status.state is PlayerState.STOPPED
    many = player.add([(TrackKind.FILE, "x", "x")] * (MAX_QUEUE + 5))
    assert len(many) == MAX_QUEUE
    assert player.add([(TrackKind.FILE, "x", "x")]) == []
    await player.close()


def test_track_status_current() -> None:
    from tandem.engine.player import PlayerStatus

    track = Track("t1", TrackKind.FILE, "x", "X")
    assert PlayerStatus(queue=(track,), index=0).current == track
    assert PlayerStatus(queue=(track,), index=3).current is None
