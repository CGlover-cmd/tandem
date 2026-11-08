"""Line speakers up automatically: measure each one's delay with the PC's microphone.

For each playing output in turn, Tandem sends a short pattern of beeps to that output alone
and listens with the default microphone. The time from sending to hearing is that output's
lag. The slowest output gets no extra delay; every other one is delayed by the difference, so
all of them play together. (The PC's own default speakers are played by Windows directly and
can't be delayed, so they're left out.)

Everything here is plain arithmetic on 16-bit PCM, with no numpy, so it runs in the
installed app. The recording stays in memory and is dropped after the measurement.
"""

from __future__ import annotations

import array
import math
from collections.abc import Sequence
from dataclasses import dataclass

from tandem.engine.audio import CHANNELS, SAMPLE_RATE

MIC_RATE = 16_000
"""Microphone sample rate (mono): plenty to time a 2 kHz beep to a few milliseconds."""
WINDOW_MS = 5
BEEP_HZ = 2_000
BEEP_MS = 60
BEEP_STARTS_MS = (0, 300, 800)
"""Three beeps with uneven gaps: a pattern room noise is unlikely to copy."""
QUIET_MS = 400
"""Listening before the beeps are sent, for the room's noise floor."""
LISTEN_SECONDS = 9.0
"""Longest lag measured (a HomePod mini was about 5 s behind)."""
ROUND_MS = 50
"""Delays are set in the slider's steps."""
TOLERANCE_MS = 40


@dataclass(frozen=True, slots=True)
class Measurement:
    lag_ms: int | None
    """Milliseconds from sending the beeps to hearing them; None if they weren't heard."""
    noisy: bool = False
    """The room was too loud before the beeps to hear them reliably."""


def beep_pattern(amplitude: float = 0.5) -> bytes:
    """The probe as Tandem's stream format (16-bit stereo at SAMPLE_RATE)."""
    total = (BEEP_STARTS_MS[-1] + BEEP_MS + 200) * SAMPLE_RATE // 1000
    samples = array.array("h", bytes(total * 2))
    beep = BEEP_MS * SAMPLE_RATE // 1000
    fade = SAMPLE_RATE // 1000 * 5  # 5 ms ramps: no clicks
    for start_ms in BEEP_STARTS_MS:
        start = start_ms * SAMPLE_RATE // 1000
        for i in range(beep):
            ramp = min(1.0, i / fade, (beep - i) / fade)
            value = amplitude * ramp * math.sin(2 * math.pi * BEEP_HZ * i / SAMPLE_RATE)
            samples[start + i] = int(value * 32767)
    stereo = array.array("h", bytes(len(samples) * 2 * CHANNELS))
    for i, value in enumerate(samples):
        for channel in range(CHANNELS):
            stereo[i * CHANNELS + channel] = value
    return stereo.tobytes()


def _envelope(pcm: bytes, rate: int) -> list[float]:
    """RMS of each WINDOW_MS window of mono 16-bit PCM, after a crude high-pass (the beep is
    2 kHz; hum and footsteps are low)."""
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    window = rate * WINDOW_MS // 1000
    out: list[float] = []
    previous = 0
    for start in range(0, len(samples) - window + 1, window):
        total = 0
        for value in samples[start : start + window]:
            diff = value - previous  # first difference: a simple high-pass
            previous = value
            total += diff * diff
        out.append(math.sqrt(total / window))
    return out


def find_pattern(pcm: bytes, rate: int = MIC_RATE, *, quiet_ms: int = QUIET_MS) -> Measurement:
    """When the beep pattern starts in a recording that began as the beeps were sent.

    The first `quiet_ms` set the room's noise floor (no speaker answers that fast). A window
    counts as a beep when it is well above that floor; the pattern is three onsets whose gaps
    match BEEP_STARTS_MS within TOLERANCE_MS.
    """
    envelope = _envelope(pcm, rate)
    quiet = max(1, quiet_ms // WINDOW_MS)
    if len(envelope) <= quiet:
        return Measurement(None)
    floor = sorted(envelope[:quiet])[quiet // 2] + 1.0
    peak = max(envelope[quiet:], default=0.0)
    if peak < floor * 3:
        return Measurement(None, noisy=floor > 400)
    threshold = floor + (peak - floor) * 0.3
    onsets: list[int] = []
    above = False
    for index, level in enumerate(envelope):
        if index < quiet:
            continue
        if level >= threshold and not above:
            onsets.append(index * WINDOW_MS)
        above = level >= threshold
    gaps = [b - BEEP_STARTS_MS[0] for b in BEEP_STARTS_MS]
    for first in onsets:
        if all(any(abs(o - (first + gap)) <= TOLERANCE_MS for o in onsets) for gap in gaps[1:]):
            return Measurement(first)
    return Measurement(None, noisy=len(onsets) > 12)


def delays_for(lags: dict[str, int]) -> dict[str, int]:
    """Extra delay per output so all of them play with the slowest one (rounded to slider
    steps, never negative)."""
    if not lags:
        return {}
    slowest = max(lags.values())
    return {
        output_id: max(0, round((slowest - lag) / ROUND_MS) * ROUND_MS)
        for output_id, lag in lags.items()
    }


def mono_from_stereo(pcm: bytes) -> bytes:  # pragma: no cover - only used with a real mic
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 4])
    return array.array("h", samples[::2]).tobytes()


def silence_ms(ms: int) -> bytes:
    return bytes(ms * SAMPLE_RATE // 1000 * 2 * CHANNELS)


def chunks(pcm: bytes, ms: int = 20) -> Sequence[bytes]:
    """Split stream-format PCM into `ms` pieces (whole frames) for real-time pushing."""
    size = ms * SAMPLE_RATE // 1000 * 2 * CHANNELS
    return [pcm[i : i + size] for i in range(0, len(pcm), size)]
