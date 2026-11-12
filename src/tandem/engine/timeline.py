"""The shared source's recent audio, by when it was captured (ADR-0022).

Outputs on PTP timing don't take audio from a queue. Each packet they send has a known play
time, and they ask this timeline for the audio captured `delay` before it. Every such output
uses the same delay, so the same moment of audio comes out of every speaker at the same time,
whatever its network or buffer.

Capture blocks arrive with jitter, so a block's time isn't its arrival time as is. Within a
run of blocks, each block starts where the previous one ended, nudged toward the arrival time
by at most one frame per block: enough to follow the sound card's clock drifting from the
PC's counter, small enough never to be heard. After a gap (WASAPI loopback sends nothing while
the PC is silent), or when arrivals wander off by more than `RESYNC_NS`, the next block is
placed at its arrival time.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

from tandem.engine.audio import FRAME_BYTES, SAMPLE_RATE

NS = 1_000_000_000
FRAME_NS = NS / SAMPLE_RATE
RESYNC_NS = 40_000_000
"""Arrivals this far from where the run predicts start a new run."""
SMOOTHING = 0.02
"""How much of each arrival's offset from the prediction feeds the running estimate."""


def now_ns() -> int:
    """The clock outputs are timed on: the PC's high-resolution counter (also the PTP clock).
    `time.monotonic` ticks only every 15.6 ms on Windows with Python 3.11."""
    return time.perf_counter_ns()


def frames_ns(frames: int) -> int:
    return frames * NS // SAMPLE_RATE


@dataclass(slots=True)
class _Chunk:
    start_ns: int
    data: bytes
    run: int

    @property
    def frames(self) -> int:
        return len(self.data) // FRAME_BYTES

    @property
    def end_ns(self) -> int:
        return self.start_ns + frames_ns(self.frames)


class CaptureTimeline:
    """Thread-safe: `push` from the capture thread, `read_at` from senders."""

    def __init__(self, *, keep_seconds: float = 6.0) -> None:
        self._keep_ns = int(keep_seconds * NS)
        self._chunks: deque[_Chunk] = deque()
        self._lock = threading.Lock()
        self._offset_ns = 0.0  # smoothed (arrival - prediction) within the current run
        self.runs = 0
        """Times the timeline started a new run (after a gap or a jump)."""

    def push(self, data: bytes, arrived_ns: int | None = None) -> None:
        """Add a captured block that finished arriving at `arrived_ns` (default: now)."""
        if not data:
            return
        if len(data) % FRAME_BYTES:
            raise ValueError("PCM data must be whole frames")
        arrived = now_ns() if arrived_ns is None else arrived_ns
        raw_start = arrived - frames_ns(len(data) // FRAME_BYTES)
        with self._lock:
            last = self._chunks[-1] if self._chunks else None
            if last is None or abs(raw_start - last.end_ns) > RESYNC_NS:
                start = raw_start
                self._offset_ns = 0.0
                self.runs += 1
            else:
                predicted = last.end_ns
                self._offset_ns += (raw_start - predicted - self._offset_ns) * SMOOTHING
                step = max(-FRAME_NS, min(FRAME_NS, self._offset_ns))
                start = predicted + round(step)
                self._offset_ns -= step
            self._chunks.append(_Chunk(start, data, self.runs))
            horizon = arrived - self._keep_ns
            while self._chunks and self._chunks[0].end_ns < horizon:
                self._chunks.popleft()

    def clear(self) -> None:
        with self._lock:
            self._chunks.clear()
            self._offset_ns = 0.0

    @property
    def latest_ns(self) -> int | None:
        """End time of the newest audio held."""
        with self._lock:
            return self._chunks[-1].end_ns if self._chunks else None

    def read_at(self, start_ns: int, frames: int) -> tuple[bytes, int]:
        """`frames` frames of the audio captured from `start_ns` on, and how many of them
        were silence filled in (nothing was captured then, or it's no longer held).

        Within a run the frames come out back to back, whatever the nudges between blocks;
        a nudge shows only as one frame skipped or repeated between two reads."""
        out = bytearray(frames * FRAME_BYTES)
        filled = 0
        pos = 0
        with self._lock:
            chunks = list(self._chunks)
        index = 0
        while pos < frames:
            at_ns = start_ns + frames_ns(pos)
            while index < len(chunks) and chunks[index].end_ns <= at_ns:
                index += 1
            if index == len(chunks):
                break
            chunk = chunks[index]
            if chunk.start_ns > at_ns:
                # Nothing captured until this chunk: leave silence up to it.
                pos += min(frames - pos, max(1, round((chunk.start_ns - at_ns) / FRAME_NS)))
                continue
            offset = min(chunk.frames - 1, round((at_ns - chunk.start_ns) / FRAME_NS))
            # Copy on through the run, frame after frame.
            while True:
                count = min(chunk.frames - offset, frames - pos)
                out[pos * FRAME_BYTES : (pos + count) * FRAME_BYTES] = chunk.data[
                    offset * FRAME_BYTES : (offset + count) * FRAME_BYTES
                ]
                pos += count
                filled += count
                if pos >= frames or index + 1 >= len(chunks):
                    break
                following = chunks[index + 1]
                if following.run != chunk.run:
                    break
                index += 1
                chunk = following
                offset = 0
            index += 1
        return bytes(out), frames - filled
