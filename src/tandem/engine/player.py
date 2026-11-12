"""Tandem's own player (Phase 6, ADR-0013): local music files and internet radio.

The player is an audio source like the PC's loopback capture: when it is the source, the
audio hub's outputs (AirPlay devices and the PC's speakers) play what it decodes. Decoding is
done by a `Decoder` from the backend (miniaudio, in `adapters`); this module keeps the queue
and the real-time pacing, so it's tested with fakes.

Tracks follow each other gaplessly: one worker thread opens the next track as the current one
ends and keeps the same real-time clock, so the outputs get one unbroken stream (the player
runs a little ahead of real time, which covers the time to open the next file).

Track titles and file names are personal: they're shown in the window, never logged.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Protocol

from tandem.engine.audio import FRAME_BYTES, SAMPLE_RATE
from tandem.engine.events import Event, EventBus

_LOGGER = logging.getLogger(__name__)

CHUNK_FRAMES = SAMPLE_RATE // 100  # 10 ms, like the loopback capture
AHEAD_SECONDS = 0.2
"""How far ahead of real time the player may decode, so a busy moment doesn't cause a gap."""
MAX_QUEUE = 500


class TrackKind(Enum):
    FILE = "file"
    RADIO = "radio"


@dataclass(frozen=True, slots=True)
class Track:
    id: str
    kind: TrackKind
    location: str
    """A file path or a stream URL. Personal: never logged."""
    title: str
    artist: str | None = None
    album: str | None = None
    art: str | None = None
    """Where the window gets artwork for it (a library album id), if anywhere."""


@dataclass(frozen=True, slots=True)
class NewTrack:
    """A track to queue; the player gives it an id."""

    kind: TrackKind
    location: str
    title: str
    artist: str | None = None
    album: str | None = None
    art: str | None = None


class PlayerState(Enum):
    STOPPED = "stopped"
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class PlayerStatus:
    state: PlayerState = PlayerState.STOPPED
    queue: tuple[Track, ...] = ()
    index: int | None = None
    position: float = 0.0
    duration: float | None = None
    error: str | None = None
    """Why the last track couldn't play (an exception type name), if it couldn't."""

    @property
    def current(self) -> Track | None:
        if self.index is None or not 0 <= self.index < len(self.queue):
            return None
        return self.queue[self.index]


@dataclass(frozen=True, slots=True)
class PlayerChanged(Event):
    status: PlayerStatus = field(default_factory=PlayerStatus)


class DecodedStream(Protocol):
    @property
    def duration(self) -> float | None:
        """Seconds, or None for radio."""
        ...

    def read(self, frames: int) -> bytes:
        """Up to `frames` frames of 44.1 kHz 16-bit stereo PCM; b"" at the end. May block."""
        ...

    def close(self) -> None: ...


Decoder = Callable[[Track], DecodedStream]
PcmSink = Callable[[bytes], None]


@dataclass(slots=True)
class _Pacing:
    """The worker's real-time clock, kept across tracks so they join without a gap."""

    started: float
    sent: int = 0  # frames


class PlayerCapture:
    """The player as the hub's `PcmCapture`: while started, decoded audio goes to `on_pcm`."""

    def __init__(self, player: Player) -> None:
        self._player = player

    def start(self, on_pcm: PcmSink) -> None:
        self._player.attach(on_pcm)

    def stop(self) -> None:
        self._player.attach(None)


class Player:
    def __init__(
        self,
        bus: EventBus,
        decoder: Decoder,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        status_interval: float = 1.0,
    ) -> None:
        self._bus = bus
        self._decoder = decoder
        self._clock = clock
        self._sleep = sleep
        self._status_interval = status_interval
        self._status = PlayerStatus()
        self._ids = itertools.count(1)
        self._sink: PcmSink | None = None
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    # --- reading ---------------------------------------------------------------------

    @property
    def status(self) -> PlayerStatus:
        return self._status

    def capture(self) -> PlayerCapture:
        return PlayerCapture(self)

    def attach(self, sink: PcmSink | None) -> None:
        with self._lock:
            self._sink = sink

    # --- the queue -------------------------------------------------------------------

    def add(self, items: Sequence[tuple[TrackKind, str, str]]) -> list[Track]:
        """Append (kind, location, title) tracks. Returns those added (the queue is capped)."""
        return self.add_tracks([NewTrack(kind, location, title) for kind, location, title in items])

    def add_tracks(self, items: Sequence[NewTrack], *, play_next: bool = False) -> list[Track]:
        """Append tracks, or put them right after the current one. Returns those added (the
        queue is capped at `MAX_QUEUE`)."""
        status = self._status
        room = MAX_QUEUE - len(status.queue)
        tracks = tuple(
            Track(f"t{next(self._ids)}", i.kind, i.location, i.title, i.artist, i.album, i.art)
            for i in list(items)[: max(0, room)]
        )
        if not tracks:
            return []
        at = len(status.queue)
        if play_next and status.index is not None:
            at = status.index + 1
        self._set(replace(status, queue=status.queue[:at] + tracks + status.queue[at:]))
        return list(tracks)

    def play_tracks(self, items: Sequence[NewTrack], start: int = 0) -> None:
        """Replace the queue with `items` and play from `start` (playing an album)."""
        self.clear()
        tracks = self.add_tracks(items)
        if tracks:
            self.play(tracks[min(max(0, start), len(tracks) - 1)].id)

    def remove(self, track_id: str) -> None:
        status = self._status
        index = next((i for i, t in enumerate(status.queue) if t.id == track_id), None)
        if index is None:
            return
        if index == status.index:
            self.stop()
            status = self._status
        queue = status.queue[:index] + status.queue[index + 1 :]
        current = status.index
        if current is not None and index < current:
            current -= 1
        if current is not None and current >= len(queue):
            current = None
        self._set(replace(status, queue=queue, index=current))

    def clear(self) -> None:
        self.stop()
        self._set(PlayerStatus())

    # --- transport -------------------------------------------------------------------

    def play(self, track_id: str | None = None) -> None:
        """Play a track from the queue (the current or first one if none is given)."""
        status = self._status
        if track_id is not None:
            index = next((i for i, t in enumerate(status.queue) if t.id == track_id), None)
        elif status.state is PlayerState.PAUSED:
            self.resume()
            return
        else:
            index = status.index if status.current is not None else (0 if status.queue else None)
        if index is None:
            return
        self._start(index)

    def pause(self) -> None:
        if self._status.state is PlayerState.PLAYING:
            self._resume.clear()
            self._set(replace(self._status, state=PlayerState.PAUSED))

    def resume(self) -> None:
        if self._status.state is PlayerState.PAUSED:
            self._set(replace(self._status, state=PlayerState.PLAYING))
            self._resume.set()

    def toggle(self) -> None:
        if self._status.state is PlayerState.PLAYING:
            self.pause()
        else:
            self.play()

    def next(self) -> None:
        index = self._status.index
        if index is not None and index + 1 < len(self._status.queue):
            self._start(index + 1)
        else:
            self.stop()

    def previous(self) -> None:
        status = self._status
        if status.index is None:
            return
        if status.position > 3 or status.index == 0:
            self._start(status.index)  # back to the start of this track
        else:
            self._start(status.index - 1)

    def stop(self) -> None:
        self._halt()
        status = self._status
        self._set(replace(status, state=PlayerState.STOPPED, position=0.0))

    async def close(self) -> None:
        self._halt()

    # --- internals -------------------------------------------------------------------

    def _start(self, index: int) -> None:
        self._halt()
        with suppress(RuntimeError):  # driven from a plain thread
            self._loop = asyncio.get_running_loop()
        track = self._status.queue[index]
        self._set(
            replace(
                self._status,
                state=PlayerState.LOADING,
                index=index,
                position=0.0,
                duration=None,
                error=None,
            )
        )
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        worker = threading.Thread(
            target=self._run, args=(track, self._stop, self._resume), name="tandem-player"
        )
        self._worker = worker
        worker.daemon = True
        worker.start()

    def _halt(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            self._stop.set()
            self._resume.set()
            if worker is not threading.current_thread():
                worker.join(timeout=0.5)

    def _run(self, track: Track, stop: threading.Event, resume: threading.Event) -> None:
        pacing = _Pacing(self._clock())
        first = True
        current: Track | None = track
        while current is not None and not stop.is_set():
            try:
                stream = self._decoder(current)
            except Exception as exc:
                _LOGGER.info("A track couldn't be opened (%s)", type(exc).__name__)
                self._from_thread(stop, self._failed, type(exc).__name__)
                return
            try:
                if first:
                    self._from_thread(stop, self._playing, stream.duration)
                else:
                    self._from_thread(stop, self._advanced, current.id, stream.duration)
                first = False
                self._pump(stream, stop, resume, pacing)
            except Exception as exc:
                _LOGGER.info("A track stopped playing (%s)", type(exc).__name__)
                self._from_thread(stop, self._failed, type(exc).__name__)
                return
            finally:
                stream.close()
            if stop.is_set():
                return
            current = self._after(current.id)
        self._from_thread(stop, self._ended)

    def _after(self, track_id: str) -> Track | None:
        """The track queued after `track_id` (read from the newest status), if any."""
        queue = self._status.queue
        index = next((i for i, t in enumerate(queue) if t.id == track_id), None)
        if index is None or index + 1 >= len(queue):
            return None
        return queue[index + 1]

    def _pump(
        self,
        stream: DecodedStream,
        stop: threading.Event,
        resume: threading.Event,
        pacing: _Pacing,
    ) -> None:
        track_start = pacing.sent  # frames sent before this track
        reported = self._clock()
        while not stop.is_set():
            if not resume.is_set():
                paused_at = self._clock()
                resume.wait()
                pacing.started += self._clock() - paused_at
                continue
            ahead = pacing.sent / SAMPLE_RATE - (self._clock() - pacing.started)
            if ahead > AHEAD_SECONDS:
                self._sleep(ahead - AHEAD_SECONDS)
                continue
            data = stream.read(CHUNK_FRAMES)
            if not data:
                return
            data = data[: len(data) - len(data) % FRAME_BYTES]
            pacing.sent += len(data) // FRAME_BYTES
            with self._lock:
                sink = self._sink
            if sink is not None:
                sink(data)
            now = self._clock()
            if now - reported >= self._status_interval:
                reported = now
                self._from_thread(stop, self._position, (pacing.sent - track_start) / SAMPLE_RATE)

    def _from_thread(self, stop: threading.Event, fn: Callable[..., None], *args: object) -> None:
        def call() -> None:
            if not stop.is_set():
                fn(*args)

        loop = self._loop
        if loop is None or loop.is_closed():
            call()
        else:
            loop.call_soon_threadsafe(call)

    def _playing(self, duration: float | None) -> None:
        state = PlayerState.PLAYING if self._resume.is_set() else PlayerState.PAUSED
        self._set(replace(self._status, state=state, duration=duration))

    def _advanced(self, track_id: str, duration: float | None) -> None:
        """The worker moved on to the next track without a gap."""
        index = next((i for i, t in enumerate(self._status.queue) if t.id == track_id), None)
        state = PlayerState.PLAYING if self._resume.is_set() else PlayerState.PAUSED
        self._set(
            replace(
                self._status, state=state, index=index, position=0.0, duration=duration, error=None
            )
        )

    def _position(self, seconds: float) -> None:
        self._set(replace(self._status, position=seconds))

    def _failed(self, reason: str) -> None:
        self._worker = None
        self._set(replace(self._status, state=PlayerState.STOPPED, error=reason))

    def _ended(self) -> None:
        self._worker = None
        self._set(replace(self._status, state=PlayerState.STOPPED, position=0.0))

    def _set(self, status: PlayerStatus) -> None:
        self._status = status
        self._bus.publish(PlayerChanged(status))
