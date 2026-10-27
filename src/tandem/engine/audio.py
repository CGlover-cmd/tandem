"""System audio to AirPlay outputs (Phase 4), protocol-agnostic.

The PC's own audio is captured by a `PcmCapture` (WASAPI loopback, in `adapters`) as 44.1 kHz,
16-bit stereo PCM, the format AirPlay audio uses. Each output gets its own `PcmBuffer`, a
bounded queue between the capture thread and that output's network sender, so one slow output
never holds up the capture or the others (ADR-0011). An `AudioSink` from the backend streams a
buffer to one connected device.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from tandem.engine.events import Event

SAMPLE_RATE = 44_100
CHANNELS = 2
SAMPLE_WIDTH = 2  # bytes, 16-bit signed little-endian
FRAME_BYTES = CHANNELS * SAMPLE_WIDTH


def frames_to_seconds(frames: int) -> float:
    return frames / SAMPLE_RATE


class PcmBuffer:
    """A jitter buffer of PCM frames from the capture thread to one network sender.

    `push` may be called from any thread. The sender reads one packet at a time, in real time,
    and must never wait: `read` returns at once, with silence when there isn't enough audio.
    It first lets `prime_seconds` of audio build up, so the capture's 10 ms blocks and the
    sender's packets don't have to line up, and skips anything older than that, so a stream
    whose receiver took a while to set up still starts live. If the buffer runs dry, it sends
    silence and primes again. If the sender falls more than `max_seconds` behind, the oldest
    audio is dropped: a live stream should stay current, not build up delay.
    """

    def __init__(self, *, max_seconds: float = 1.0, prime_seconds: float = 0.1) -> None:
        if not 0 <= prime_seconds < max_seconds:
            raise ValueError("need 0 <= prime_seconds < max_seconds")
        self._max_bytes = int(max_seconds * SAMPLE_RATE) * FRAME_BYTES
        self._prime_frames = int(prime_seconds * SAMPLE_RATE)
        self._chunks: deque[bytes] = deque()
        self._size = 0  # bytes held, including the consumed part of the first chunk
        self._head = 0  # bytes already consumed from the first chunk
        self._lock = threading.Lock()
        self._primed = False
        self._closed = False
        self.pushed_frames = 0
        self.dropped_frames = 0
        self.silent_frames = 0
        self.sent_frames = 0
        self.underruns = 0
        self.trimmed_frames = 0
        """Old audio skipped when (re)starting, so the stream starts live."""

    @property
    def buffered_frames(self) -> int:
        with self._lock:
            return (self._size - self._head) // FRAME_BYTES

    @property
    def closed(self) -> bool:
        return self._closed

    def push(self, data: bytes) -> None:
        """Add captured PCM. Thread-safe; partial frames are not allowed."""
        if self._closed or not data:
            return
        if len(data) % FRAME_BYTES:
            raise ValueError("PCM data must be whole frames")
        with self._lock:
            self._chunks.append(data)
            self._size += len(data)
            self.pushed_frames += len(data) // FRAME_BYTES
            excess = (self._size - self._head) - self._max_bytes
            if excess > 0:
                self._discard(excess)

    def close(self) -> None:
        self._closed = True

    def _discard(self, nbytes: int) -> None:
        # Lock held. Drop the oldest `nbytes` (a whole number of frames).
        self.dropped_frames += nbytes // FRAME_BYTES
        self._consume(nbytes)

    def _consume(self, nbytes: int) -> bytes:
        # Lock held. Remove and return the oldest `nbytes`.
        out = bytearray()
        while self._chunks and len(out) < nbytes:
            chunk = self._chunks[0]
            piece = chunk[self._head : self._head + nbytes - len(out)]
            out += piece
            self._head += len(piece)
            if self._head >= len(chunk):
                self._chunks.popleft()
                self._size -= len(chunk)
                self._head = 0
        return bytes(out)

    async def read(self, frames: int) -> bytes:
        """Exactly `frames` frames, at once: audio when enough is buffered, else silence.
        Returns b"" once closed and empty."""
        nbytes = frames * FRAME_BYTES
        with self._lock:
            available = (self._size - self._head) // FRAME_BYTES
            if self._closed and available == 0:
                return b""
            if not self._primed and (available >= self._prime_frames + frames or self._closed):
                self._primed = True
                # Audio that piled up before the sender started (while the receiver was
                # setting up) would only add delay. Keep just the cushion and go live.
                backlog = available - self._prime_frames - frames
                if backlog > 0 and not self._closed:
                    self._consume(backlog * FRAME_BYTES)
                    self.trimmed_frames += backlog
                    available -= backlog
            if self._primed and available >= frames:
                self.sent_frames += frames
                return self._consume(nbytes)
            if self._primed and not self._closed:
                self._primed = False  # ran dry: send silence and build up again
                self.underruns += 1
            if self._closed:
                tail = self._consume(nbytes)
                self.sent_frames += len(tail) // FRAME_BYTES
                return tail + bytes(nbytes - len(tail))
            self.silent_frames += frames
            return bytes(nbytes)


class PcmCapture(Protocol):
    """Captures the PC's audio as 44.1 kHz, 16-bit stereo PCM."""

    def start(self, on_pcm: Callable[[bytes], None]) -> None:
        """Begin calling `on_pcm` (from a capture thread) with whole frames."""

    def stop(self) -> None: ...


class AudioSink(Protocol):
    """Streams PCM to one connected device."""

    async def play(self, buffer: PcmBuffer, *, title: str, artist: str) -> None:
        """Stream until the buffer closes or the task is cancelled. Raises on failure."""

    async def set_volume(self, level: float) -> None: ...


class StreamState(Enum):
    STARTING = "starting"
    STREAMING = "streaming"
    WAITING = "waiting"  # connection dropped; resumes when it reconnects
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AudioStreamChanged(Event):
    device_id: str
    state: StreamState
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class AudioStats:
    sent_seconds: float
    dropped_seconds: float
    silence_seconds: float
    """Silence sent because no captured audio was ready (not silence in the audio itself)."""
    buffered_ms: float
    underruns: int
    """Times the buffer ran dry mid-stream (each is a short gap)."""


class AudioError(Exception):
    """Audio can't start or continue. `str()` is safe to show."""
