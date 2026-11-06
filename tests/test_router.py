"""Multi-output routing (Phase 5): PC outputs, per-output volume and delay, source switching."""

from __future__ import annotations

import asyncio
import struct

import pytest

from conftest import FakeBackend, FakeSink, ManualSleep, make_device
from tandem.engine.audio import (
    FRAME_BYTES,
    SAMPLE_RATE,
    AudioError,
    AudioStreamChanged,
    PcmBuffer,
    StreamState,
    apply_gain,
)
from tandem.engine.audio_hub import BASE_DELAY, MAX_DELAY_MS, is_local
from tandem.engine.service import AudioSource, Engine

SPEAKER = make_device()
SOUNDBAR = make_device(id="AA:BB:CC:00:00:02", name="Den Soundbar", address="192.0.2.11")


def frames(n: int, value: int = 1000) -> bytes:
    return struct.pack("<hh", value, value) * n


async def _wait(predicate: object, *, tries: int = 500) -> None:
    for _ in range(tries):
        if callable(predicate) and predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition not reached")


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend([SPEAKER, SOUNDBAR])


# --- helpers in audio.py -------------------------------------------------------------------


def test_gain_scales_and_clips_to_silence() -> None:
    pcm = frames(4, 10_000)
    assert apply_gain(pcm, 100) == pcm
    assert apply_gain(pcm, 0) == bytes(len(pcm))
    half = struct.unpack("<h", apply_gain(pcm, 50)[:2])[0]
    assert half == 2500  # (50 / 100) ** 2 of the level


async def test_buffer_delay_can_change_while_streaming() -> None:
    buffer = PcmBuffer(max_seconds=2.0, prime_seconds=0.0)
    buffer.push(frames(441))
    assert await buffer.read(441) == frames(441)
    buffer.set_delay(0.02)  # 882 frames of cushion now
    assert buffer.delay_seconds == pytest.approx(0.02)
    buffer.push(frames(882))
    assert await buffer.read(441) == bytes(441 * FRAME_BYTES)  # building up the cushion
    buffer.push(frames(441))
    assert await buffer.read(441) == frames(441)
    with pytest.raises(ValueError, match="negative"):
        buffer.set_delay(-1)


def test_local_ids() -> None:
    assert is_local("local:abc")
    assert not is_local(SPEAKER.id)


# --- the engine's outputs ----------------------------------------------------------------


async def test_local_outputs_hide_the_captured_device_for_system_audio(
    backend: FakeBackend,
) -> None:
    engine = Engine(backend)
    assert [o.id for o in engine.local_outputs()] == ["local:headphones"]
    await engine.set_audio_source(AudioSource.PLAYER)
    assert [o.id for o in engine.local_outputs()] == ["local:speakers", "local:headphones"]
    await engine.close()


async def test_airplay_and_pc_outputs_play_together(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    engine = Engine(backend, sleep=manual_sleep)
    await engine.start_output(SPEAKER.id, volume=40, delay_ms=0)
    await engine.start_output("local:headphones", volume=70, delay_ms=0)
    (airplay,) = backend.sinks[SPEAKER.id]
    (local,) = backend.local_sinks["local:headphones"]
    await airplay.playing.wait()
    await local.playing.wait()
    (capture,) = backend.captures  # one capture feeds both
    for _ in range(30):
        capture.feed(frames(441))
    await _wait(lambda: len(airplay.received) > 0 and len(local.received) > 0)
    on = engine.outputs_on()
    assert set(on) == {SPEAKER.id, "local:headphones"}
    assert on["local:headphones"] == (StreamState.STREAMING, 70, 0)
    assert local.volumes == [70]
    await engine.stop_output("local:headphones")
    assert not capture.stopped  # the AirPlay output still needs it
    await engine.stop_output(SPEAKER.id)
    assert capture.stopped
    await engine.close()


async def test_volume_and_delay_per_output(backend: FakeBackend, manual_sleep: ManualSleep) -> None:
    engine = Engine(backend, sleep=manual_sleep)
    events: list[AudioStreamChanged] = []
    engine.bus.subscribe(AudioStreamChanged, events.append)
    await engine.start_output(SPEAKER.id, delay_ms=500)
    (sink,) = backend.sinks[SPEAKER.id]
    await sink.playing.wait()
    assert sink.buffer is not None
    assert sink.buffer.delay_seconds == pytest.approx(BASE_DELAY + 0.5)

    await engine.set_output_volume(SPEAKER.id, 25)
    assert sink.volumes[-1] == 25
    engine.set_output_delay(SPEAKER.id, MAX_DELAY_MS + 5000)  # clamped
    assert engine.outputs_on()[SPEAKER.id][2] == MAX_DELAY_MS
    assert sink.buffer.delay_seconds == pytest.approx(BASE_DELAY + MAX_DELAY_MS / 1000)
    with pytest.raises(ValueError, match="volume"):
        await engine.set_output_volume(SPEAKER.id, 120)
    with pytest.raises(AudioError):
        await engine.set_output_volume(SOUNDBAR.id, 10)
    with pytest.raises(AudioError):
        engine.set_output_delay(SOUNDBAR.id, 10)
    assert events[-1].state is StreamState.STREAMING
    await engine.close()


async def test_unknown_or_vanished_pc_output(backend: FakeBackend) -> None:
    class Vanishing(FakeBackend):
        def local_sink(self, output_id: str) -> FakeSink | None:
            return None  # listed, but gone by the time it opens

    engine = Engine(backend)
    with pytest.raises(AudioError):
        await engine.start_output("local:speakers")  # the captured device, with system audio
    await engine.close()

    engine = Engine(Vanishing([SPEAKER]))
    states: list[tuple[str, StreamState]] = []
    engine.bus.subscribe(AudioStreamChanged, lambda e: states.append((e.device_id, e.state)))
    await engine.start_output("local:headphones")
    assert ("local:headphones", StreamState.FAILED) in states
    assert "local:headphones" not in engine.outputs_on()
    await engine.close()


async def test_switching_source_keeps_outputs_and_drops_the_feedback_one(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    engine = Engine(backend, sleep=manual_sleep)
    await engine.set_audio_source(AudioSource.PLAYER)
    await engine.set_audio_source(AudioSource.PLAYER)  # no change
    await engine.start_output("local:speakers")
    await engine.start_output(SPEAKER.id)
    assert backend.captures == []  # the player is the source, not loopback
    await engine.set_audio_source(AudioSource.SYSTEM)
    assert set(engine.outputs_on()) == {SPEAKER.id}  # default speakers would echo: off
    assert len(backend.captures) == 1
    await engine.set_audio_source(AudioSource.PLAYER)
    assert backend.captures[0].stopped
    await engine.close()


async def test_pc_output_delay_holds_audio_back(
    backend: FakeBackend, manual_sleep: ManualSleep
) -> None:
    engine = Engine(backend, sleep=manual_sleep)
    await engine.start_output("local:headphones", delay_ms=200)
    (sink,) = backend.local_sinks["local:headphones"]
    await sink.playing.wait()
    (capture,) = backend.captures
    capture.feed(frames(int(0.25 * SAMPLE_RATE)))  # not yet 300 ms
    for _ in range(20):
        await asyncio.sleep(0)
    assert frames(10) not in sink.received
    capture.feed(frames(int(0.1 * SAMPLE_RATE)))
    await _wait(lambda: frames(10) in sink.received)
    await engine.close()
