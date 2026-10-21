from __future__ import annotations

import asyncio
import struct
import threading
import time

import pytest

from conftest import FakeBackend, ManualSleep, make_device
from tandem.engine.audio import (
    FRAME_BYTES,
    SAMPLE_RATE,
    AudioError,
    AudioStreamChanged,
    PcmBuffer,
    StreamState,
)
from tandem.engine.service import Engine

SPEAKER = make_device()


def frames(n: int, value: int = 1000) -> bytes:
    return struct.pack("<hh", value, value) * n


# --- PcmBuffer ---------------------------------------------------------------------------


async def test_buffer_primes_before_sending() -> None:
    buffer = PcmBuffer(prime_seconds=0.01)  # 441 frames
    buffer.push(frames(400))
    assert await buffer.read(352) == bytes(352 * FRAME_BYTES)  # not primed yet: silence
    buffer.push(frames(400))
    assert await buffer.read(352) == frames(352)
    assert buffer.sent_frames == 352
    assert buffer.silent_frames == 352


async def test_buffer_underrun_sends_silence_and_reprimes() -> None:
    buffer = PcmBuffer(prime_seconds=0.0)
    buffer.push(frames(500))
    assert await buffer.read(352) == frames(352)
    assert await buffer.read(352) == bytes(352 * FRAME_BYTES)  # 148 left: underrun
    assert buffer.underruns == 1
    assert buffer.buffered_frames == 148  # kept, not thrown away
    buffer.push(frames(300))
    assert await buffer.read(352) == frames(352)


async def test_buffer_drops_oldest_when_reader_lags() -> None:
    buffer = PcmBuffer(max_seconds=0.02, prime_seconds=0.0)  # 882 frames
    buffer.push(frames(600, 1))
    buffer.push(frames(600, 2))
    assert buffer.buffered_frames == 882
    assert buffer.dropped_frames == 318
    data = await buffer.read(282)
    assert data == frames(282, 1)  # the oldest surviving audio comes out first
    assert await buffer.read(600) == frames(600, 2)


async def test_buffer_close_drains_then_ends() -> None:
    buffer = PcmBuffer(prime_seconds=0.05)
    buffer.push(frames(100))
    buffer.close()
    tail = await buffer.read(352)
    assert tail == frames(100) + bytes(252 * FRAME_BYTES)
    assert await buffer.read(352) == b""
    buffer.push(frames(10))  # ignored once closed
    assert buffer.buffered_frames == 0


def test_buffer_rejects_partial_frames_and_bad_settings() -> None:
    buffer = PcmBuffer()
    with pytest.raises(ValueError, match="whole frames"):
        buffer.push(b"\x00\x01\x02")
    buffer.push(b"")
    with pytest.raises(ValueError, match="prime"):
        PcmBuffer(max_seconds=0.1, prime_seconds=0.2)


async def test_buffer_push_from_another_thread() -> None:
    buffer = PcmBuffer(max_seconds=5.0, prime_seconds=0.0)

    def producer() -> None:
        for _ in range(100):
            buffer.push(frames(441))

    thread = threading.Thread(target=producer)
    thread.start()
    received = 0
    deadline = time.monotonic() + 5
    while received < 100 * 441 and time.monotonic() < deadline:
        data = await buffer.read(441)
        if data != bytes(len(data)):
            received += 441
        await asyncio.sleep(0)
    thread.join()
    assert received == 100 * 441
    assert buffer.dropped_frames == 0


# --- Engine audio ------------------------------------------------------------------------


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend([SPEAKER])


async def _wait(predicate: object, *, tries: int = 500) -> None:
    for _ in range(tries):
        if callable(predicate) and predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition not reached")


async def test_stream_starts_and_sends_captured_audio(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    engine = Engine(backend, sleep=manual_sleep)
    states: list[StreamState] = []
    engine.bus.subscribe(AudioStreamChanged, lambda e: states.append(e.state))
    await engine.start_audio(SPEAKER.id, volume=35, timeout=1)
    (sink,) = backend.sinks[SPEAKER.id]
    await sink.playing.wait()
    assert sink.volumes == [35]
    assert sink.titles == [("This PC", "Tandem")]
    (capture,) = backend.captures
    for _ in range(20):
        capture.feed(frames(441))  # 200 ms of audio
    await _wait(lambda: frames(441) in sink.received)
    assert engine.streaming_audio(SPEAKER.id)
    stats = engine.audio_stats(SPEAKER.id)
    assert stats is not None
    assert stats.sent_seconds > 0
    await engine.stop_audio(SPEAKER.id)
    assert capture.stopped
    assert states[:2] == [StreamState.STARTING, StreamState.STREAMING]
    assert states[-1] is StreamState.STOPPED
    assert engine.audio_stats(SPEAKER.id) is None
    await engine.close()


async def test_start_is_idempotent_and_volume_is_checked(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    engine = Engine(backend, sleep=manual_sleep)
    with pytest.raises(ValueError, match="volume"):
        await engine.start_audio(SPEAKER.id, volume=101, timeout=1)
    await engine.start_audio(SPEAKER.id, timeout=1)
    await engine.start_audio(SPEAKER.id, timeout=1)
    assert len(backend.captures) == 1
    await engine.stop_audio(SPEAKER.id)
    await engine.stop_audio(SPEAKER.id)  # already stopped: harmless
    await engine.close()


async def test_stream_resumes_after_the_connection_drops(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    engine = Engine(backend, sleep=manual_sleep)
    states: list[tuple[StreamState, str | None]] = []
    engine.bus.subscribe(AudioStreamChanged, lambda e: states.append((e.state, e.reason)))
    await engine.start_audio(SPEAKER.id, timeout=1)
    first = backend.sinks[SPEAKER.id][0]
    await first.playing.wait()
    first_buffer = first.buffer
    backend.lost_callbacks[SPEAKER.id](ConnectionResetError())
    await manual_sleep.until(1)  # the session waits before reconnecting
    manual_sleep.release()
    await _wait(lambda: len(backend.sinks[SPEAKER.id]) == 2)
    second = backend.sinks[SPEAKER.id][1]
    await second.playing.wait()
    assert second.buffer is not first_buffer  # a fresh buffer: no stale audio
    assert first_buffer is not None
    assert first_buffer.closed
    assert states.count((StreamState.STREAMING, None)) == 2
    assert (StreamState.WAITING, "ConnectionResetError") in states
    assert len(backend.captures) == 1  # the capture kept running throughout
    await engine.close()


async def test_stream_error_retries_with_backoff(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    backend.sink_failures[SPEAKER.id] = [OSError("receiver went away")]
    engine = Engine(backend, sleep=manual_sleep)
    reasons: list[str | None] = []
    engine.bus.subscribe(
        AudioStreamChanged,
        lambda e: reasons.append(e.reason) if e.state is StreamState.WAITING else None,
    )
    await engine.start_audio(SPEAKER.id, timeout=1)
    await _wait(lambda: reasons == ["OSError"])
    # The retry runs on a timer (about a second); give it real time.
    await asyncio.wait_for(_until_sinks(backend, 2), timeout=5)
    await backend.sinks[SPEAKER.id][1].playing.wait()
    await engine.close()


async def _until_sinks(backend: FakeBackend, count: int) -> None:
    while len(backend.sinks.get(SPEAKER.id, [])) < count:  # noqa: ASYNC110
        await asyncio.sleep(0.05)


async def test_disconnect_stops_the_stream(backend: FakeBackend, manual_sleep: ManualSleep) -> None:
    engine = Engine(backend, sleep=manual_sleep)
    states: list[StreamState] = []
    engine.bus.subscribe(AudioStreamChanged, lambda e: states.append(e.state))
    await engine.start_audio(SPEAKER.id, timeout=1)
    await backend.sinks[SPEAKER.id][0].playing.wait()
    await engine.disconnect(SPEAKER.id)
    await _wait(lambda: bool(states) and states[-1] is StreamState.STOPPED)
    assert not engine.streaming_audio(SPEAKER.id)
    assert backend.captures[0].stopped
    await engine.close()


async def test_device_without_audio_fails(backend: FakeBackend, manual_sleep: ManualSleep) -> None:
    backend.audio_enabled = False
    engine = Engine(backend, sleep=manual_sleep)
    reasons: list[str | None] = []
    engine.bus.subscribe(
        AudioStreamChanged,
        lambda e: reasons.append(e.reason) if e.state is StreamState.FAILED else None,
    )
    await engine.start_audio(SPEAKER.id, timeout=1)
    assert reasons == ["NoAudioOutput"]
    assert not engine.streaming_audio(SPEAKER.id)
    assert backend.captures[0].stopped
    await engine.close()


async def test_start_needs_a_connection(backend: FakeBackend) -> None:
    from tandem.engine.audio_hub import AudioHub
    from tandem.engine.events import EventBus

    hub = AudioHub(EventBus(), backend.capture, backend.audio_sink, lambda _id: None)
    with pytest.raises(AudioError, match="not connected"):
        hub.start(SPEAKER.id)


def test_odd_capture_blocks_are_trimmed_to_whole_frames(backend: FakeBackend) -> None:
    from tandem.engine.audio_hub import AudioHub
    from tandem.engine.events import EventBus

    hub = AudioHub(EventBus(), backend.capture, backend.audio_sink, lambda _id: None)
    buffer = PcmBuffer()
    hub._buffers = (buffer,)  # pyright: ignore[reportPrivateUsage]
    hub._fan_out(frames(10) + b"\x01\x02")  # pyright: ignore[reportPrivateUsage]
    assert buffer.buffered_frames == 10
    assert SAMPLE_RATE == 44_100
