"""Lining speakers up with the microphone: the beep pattern, finding it, and the delays."""

from __future__ import annotations

import array
import asyncio
import math
import random
from pathlib import Path

from conftest import FakeBackend, make_device
from tandem import bridge
from tandem.engine import lineup
from tandem.engine.audio import FRAME_BYTES
from tandem.engine.events import EventBus
from tandem.engine.service import Engine
from tandem.engine.settings import SettingsStore
from tandem.ui import backend as ui

PATIO = make_device(id="AA:BB:CC:00:00:21", name="Patio Speaker")
LOFT = make_device(id="AA:BB:CC:00:00:22", name="Loft Speaker")


def recording(lag_ms: int | None, *, noise: float = 150, amplitude: float = 6000) -> bytes:
    """What the microphone hears: room noise, then the beeps `lag_ms` after they were sent
    (which is QUIET_MS after the recording starts)."""
    rate = lineup.MIC_RATE
    total = int(lineup.LISTEN_SECONDS * rate)
    rng = random.Random(7)
    samples = array.array("h", (int(rng.gauss(0, noise)) for _ in range(total)))
    if lag_ms is not None:
        for start_ms in lineup.BEEP_STARTS_MS:
            start = (lineup.QUIET_MS + lag_ms + start_ms) * rate // 1000
            for i in range(lineup.BEEP_MS * rate // 1000):
                if start + i < total:
                    beep = amplitude * math.sin(2 * math.pi * lineup.BEEP_HZ * i / rate)
                    samples[start + i] = max(-32768, min(32767, samples[start + i] + int(beep)))
    return samples.tobytes()


def test_the_probe_is_whole_frames_in_stream_format() -> None:
    probe = lineup.beep_pattern()
    assert len(probe) % FRAME_BYTES == 0
    assert all(len(c) % FRAME_BYTES == 0 for c in lineup.chunks(probe))
    assert lineup.silence_ms(10) == bytes(len(lineup.silence_ms(10)))


def test_the_beeps_are_found_at_their_lag() -> None:
    for lag in (900, 2500, 5200, 7000):
        found = lineup.find_pattern(recording(lag))
        assert found.lag_ms is not None
        assert abs(found.lag_ms - lineup.QUIET_MS - lag) <= lineup.WINDOW_MS
    assert lineup.find_pattern(recording(None)).lag_ms is None
    loud = lineup.find_pattern(recording(3000, noise=6000, amplitude=3000))
    assert loud.lag_ms is None
    assert loud.noisy
    assert lineup.find_pattern(b"").lag_ms is None


def test_delays_bring_everyone_to_the_slowest() -> None:
    assert lineup.delays_for({"a": 2140, "b": 5230, "c": 2390}) == {"a": 3100, "b": 0, "c": 2850}
    assert lineup.delays_for({}) == {}


async def _fast(_delay: float) -> None:
    await asyncio.sleep(0)


async def _playing(tmp_path: Path, fake: FakeBackend) -> tuple[Engine, bridge.EngineBackend]:
    bus = EventBus()
    engine = Engine(fake, bus=bus, sleep=_fast)
    backend = bridge.EngineBackend(engine, SettingsStore(tmp_path / "s.json", bus))
    await backend.start()
    for speaker in (PATIO, LOFT):
        await backend.set_output(speaker.id, True)
    for _ in range(50):
        states = [o.state for o in backend.audio().outputs if o.id in (PATIO.id, LOFT.id)]
        if all(state is ui.OutputState.STREAMING for state in states):
            break
        await asyncio.sleep(0)
    return engine, backend


async def test_line_up_sets_the_delays(tmp_path: Path) -> None:
    fake = FakeBackend([PATIO, LOFT])
    fake.mic_recordings = [recording(2500), recording(4800)]
    engine, backend = await _playing(tmp_path, fake)
    await backend.line_up()
    assert backend.audio().lineup.state is ui.LineUpState.DONE
    delays = {o.id: o.delay_ms for o in backend.audio().outputs}
    first, second = sorted(engine.outputs_on())  # measured in this order
    assert abs(delays[first] - delays[second]) in (2250, 2300, 2350)
    assert min(delays[first], delays[second]) == 0
    await backend.stop()


async def test_line_up_says_what_went_wrong(tmp_path: Path) -> None:
    fake = FakeBackend([PATIO, LOFT])
    fake.mic_recordings = [recording(2500), recording(None)]
    _, backend = await _playing(tmp_path, fake)
    await backend.line_up()
    lineup_state = backend.audio().lineup
    assert lineup_state.state is ui.LineUpState.FAILED
    assert lineup_state.problem is ui.LineUpProblem.NOT_HEARD
    assert lineup_state.output in {"Patio Speaker", "Loft Speaker"}

    fake.mic_missing = True
    await backend.line_up()
    assert backend.audio().lineup.problem is ui.LineUpProblem.NO_MIC

    await backend.set_output(LOFT.id, False)
    await backend.line_up()
    assert backend.audio().lineup.problem is ui.LineUpProblem.TOO_FEW
    await backend.stop()
