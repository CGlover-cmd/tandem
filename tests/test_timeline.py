from __future__ import annotations

import struct

import pytest

from tandem.engine import timeline
from tandem.engine.audio import FRAME_BYTES
from tandem.engine.timeline import NS, CaptureTimeline, frames_ns

BLOCK = 441  # 10 ms
WRAP = 30_000  # frame numbers wrap to fit 16-bit samples


def _block(start_value: int, frames: int = BLOCK) -> bytes:
    """Frames numbered start_value, start_value+1, ... (left = right), so reads show order."""
    return b"".join(
        struct.pack("<hh", v % WRAP, v % WRAP) for v in range(start_value, start_value + frames)
    )


def _values(pcm: bytes) -> list[int]:
    return [struct.unpack_from("<h", pcm, i)[0] for i in range(0, len(pcm), FRAME_BYTES)]


def _feed(tl: CaptureTimeline, blocks: int, t0: int, jitter: list[int] | None = None) -> None:
    for n in range(blocks):
        end = t0 + frames_ns((n + 1) * BLOCK) + (jitter[n % len(jitter)] if jitter else 0)
        tl.push(_block(n * BLOCK), end)


def test_reads_are_contiguous_across_blocks() -> None:
    tl = CaptureTimeline()
    _feed(tl, 20, 1_000 * NS)
    # Read 352-frame packets across block boundaries, on exact frame times.
    out: list[int] = []
    for k in range(20):
        data, silent = tl.read_at(1_000 * NS + frames_ns(k * 352), 352)
        assert silent == 0
        out += _values(data)
    assert out == [v % WRAP for v in range(20 * 352)]
    assert tl.runs == 1


def test_jittery_arrivals_stay_contiguous() -> None:
    tl = CaptureTimeline()
    # Arrivals late by 0 to 6 ms, unevenly: the run absorbs it.
    _feed(tl, 50, 5 * NS, jitter=[0, 4_000_000, 1_000_000, 6_000_000, 2_000_000])
    assert tl.runs == 1
    data, _ = tl.read_at(5 * NS + frames_ns(10 * BLOCK), 20 * BLOCK)
    values = _values(data)
    # Within one read the frames run back to back: no filled-in gaps.
    assert values == [(values[0] + i) % WRAP for i in range(len(values))]
    # Packet after packet, a nudge costs at most one frame skipped or repeated.
    previous = None
    for k in range(40):
        data, silent = tl.read_at(5 * NS + frames_ns(10 * BLOCK + k * 352), 352)
        assert silent == 0
        first = _values(data)[0]
        if previous is not None:
            assert (first - previous) % WRAP in {351, 352, 353}
        previous = first


def test_drift_is_followed_one_frame_at_a_time() -> None:
    tl = CaptureTimeline()
    # The sound card runs 0.1% fast against the counter (far more than real ones drift):
    # arrivals come early, steadily.
    t = 0
    for n in range(500):
        t += int(frames_ns(BLOCK) * 0.999)
        tl.push(_block(n * BLOCK), t)
    assert tl.runs == 1
    latest = tl.latest_ns
    assert latest is not None
    # The run tracks the arrivals instead of running away from them.
    assert abs(latest - t) < 2_000_000


def test_gap_starts_a_new_run_with_silence_between() -> None:
    tl = CaptureTimeline()
    tl.push(_block(0), 1 * NS)
    tl.push(_block(1000), 2 * NS)  # a second later: the PC was silent meanwhile
    assert tl.runs == 2
    start = 1 * NS - frames_ns(BLOCK)
    data, silent = tl.read_at(start, 44_100 + BLOCK)
    values = _values(data)
    assert values[:BLOCK] == list(range(BLOCK))
    assert silent == 44_100 - BLOCK
    assert values[-BLOCK:] == list(range(1000, 1000 + BLOCK))


def test_reading_nothing_captured_is_silence() -> None:
    tl = CaptureTimeline()
    assert tl.latest_ns is None
    data, silent = tl.read_at(0, 352)
    assert data == bytes(352 * FRAME_BYTES)
    assert silent == 352


def test_old_audio_is_dropped() -> None:
    tl = CaptureTimeline(keep_seconds=1.0)
    tl.push(_block(0), 1 * NS)
    tl.push(_block(500), 3 * NS)
    _, silent = tl.read_at(1 * NS - frames_ns(BLOCK), BLOCK)
    assert silent == BLOCK


def test_clear_and_bad_input() -> None:
    tl = CaptureTimeline()
    tl.push(b"")  # ignored
    tl.push(_block(0))  # stamped now
    assert tl.latest_ns is not None
    tl.clear()
    assert tl.latest_ns is None
    with pytest.raises(ValueError, match="whole frames"):
        tl.push(b"\x00\x01\x02")


def test_clock_is_the_high_resolution_counter() -> None:
    a = timeline.now_ns()
    assert timeline.now_ns() >= a
