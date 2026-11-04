# pyright: basic
# (cffi objects have no types; strict mode would flag every line of the FFI calls.)
"""The PC's own sound outputs as audio outputs (Phase 5, ADR-0015), via miniaudio.

Each playback device Windows offers (speakers, headphones, a USB DAC) can be an output next to
the AirPlay devices. Its stream is delayed by the output's buffer, so it can be lined up with
AirPlay receivers, which buffer for a second or more.

Playing to the device that loopback captures would feed the sound back into itself, so while
the source is the PC's own audio the engine only offers the other devices (ADR-0005: set a
virtual cable as the Windows default, then play the delayed audio to the real speakers).
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Generator
from typing import Any

from tandem.engine.audio import (
    CHANNELS,
    FRAME_BYTES,
    SAMPLE_RATE,
    AudioError,
    PcmBuffer,
    apply_gain,
)
from tandem.engine.audio_hub import LOCAL_PREFIX
from tandem.engine.models import LocalOutput

_PERIOD_MS = 20


def output_id(name: str) -> str:
    """A stable id for a sound output, from its name (names are hardware descriptions)."""
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
    return f"{LOCAL_PREFIX}{digest}"


def _devices() -> list[tuple[LocalOutput, Any]]:  # pragma: no cover - needs sound hardware
    import _miniaudio  # pyright: ignore[reportMissingModuleSource]
    import miniaudio

    ffi: Any = _miniaudio.ffi  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    lib: Any = _miniaudio.lib  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    context: Any = miniaudio.Devices()
    found: list[tuple[LocalOutput, Any]] = []
    with ffi.new("ma_device_info**") as infos, ffi.new("ma_uint32*") as count:
        result = lib.ma_context_get_devices(context._context, infos, count, ffi.NULL, ffi.NULL)
        if result != lib.MA_SUCCESS:
            raise AudioError("can't list the PC's sound outputs")
        for i in range(count[0]):
            info = infos[0][i]
            name = ffi.string(info.name).decode(errors="replace")
            device_id = ffi.new("ma_device_id *", info.id)
            found.append((LocalOutput(output_id(name), name, bool(info.isDefault)), device_id))
    # Keep the context alive as long as the ids are used.
    found_with_context: list[tuple[LocalOutput, Any]] = [(o, (d, context)) for o, d in found]
    return found_with_context


def list_outputs() -> list[LocalOutput]:  # pragma: no cover - needs sound hardware
    try:
        return [output for output, _ in _devices()]
    except Exception:
        return []


class LocalPlaybackSink:  # pragma: no cover - needs sound hardware; checked by hand
    """Plays an output's buffer on one of the PC's sound devices."""

    def __init__(self, output: str) -> None:
        self._output = output
        self._volume = 100.0

    async def set_volume(self, level: float) -> None:
        self._volume = max(0.0, min(100.0, level))

    async def play(self, buffer: PcmBuffer, *, title: str, artist: str) -> None:
        import miniaudio

        match = next(((o, d) for o, d in _devices() if o.id == self._output), None)
        if match is None:
            raise AudioError("that sound output is gone")
        device_id, _context = match[1]

        def frames() -> Generator[bytes, int, None]:
            wanted = yield b""
            while True:
                data = buffer.read_now(wanted)
                if not data:
                    data = bytes(wanted * FRAME_BYTES)
                wanted = yield apply_gain(data, self._volume)

        device: Any = miniaudio.PlaybackDevice(
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=CHANNELS,
            sample_rate=SAMPLE_RATE,
            buffersize_msec=_PERIOD_MS,
            device_id=device_id,
        )
        stream = frames()
        next(stream)
        device.start(stream)
        try:
            while not buffer.closed:  # noqa: ASYNC110 - closed from another task
                await asyncio.sleep(0.25)
        finally:
            device.close()
