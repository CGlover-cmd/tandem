"""Live PCM into pyatv's AirPlay audio sender (ADR-0011).

pyatv's `stream_file` only takes files, URLs or byte streams it decodes itself, and its
decoder can't open an endless live stream. It does accept any `AudioSource` internally, so
this module hands it one that reads raw PCM from a `PcmBuffer`. The hand-over goes through
`pyatv.protocols.raop.open_source`, wrapped once: our source passes through, everything else
goes to pyatv's own function. pyatv is pinned to a minor version, and a test checks the hook
point still exists.
"""

from __future__ import annotations

import array
import sys
from typing import Any

import pyatv.protocols.raop as raop
from pyatv.interface import AppleTV, MediaMetadata
from pyatv.protocols.raop.audio_source import AudioSource

from tandem.engine.audio import (
    CHANNELS,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    AudioError,
    PcmBuffer,
)


def to_network_order(pcm: bytes) -> bytes:
    """16-bit samples in the byte order pyatv's sender expects: big-endian. pyatv's own sources
    swap little-endian samples the same way before sending (`_to_audio_samples`)."""
    if not pcm or sys.byteorder != "little":
        return pcm
    samples = array.array("h", pcm)
    samples.byteswap()
    return samples.tobytes()


class LivePcmSource(AudioSource):
    def __init__(self, buffer: PcmBuffer, metadata: MediaMetadata) -> None:
        self._buffer = buffer
        self._metadata = metadata

    async def readframes(self, nframes: int) -> bytes:
        return to_network_order(await self._buffer.read(nframes))

    async def get_metadata(self) -> MediaMetadata:
        return self._metadata

    async def close(self) -> None:
        self._buffer.close()

    @property
    def sample_rate(self) -> int:
        return SAMPLE_RATE

    @property
    def channels(self) -> int:
        return CHANNELS

    @property
    def sample_size(self) -> int:
        return SAMPLE_WIDTH

    @property
    def duration(self) -> int:
        return 0  # live: no end


# Looked up and replaced by name: pyatv doesn't export it.
_original_open_source: Any = getattr(raop, "open_source")  # noqa: B009


async def _open_source(source: Any, sample_rate: int, channels: int, sample_size: int) -> Any:
    if isinstance(source, LivePcmSource):
        if (sample_rate, channels, sample_size) != (SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH):
            raise AudioError(
                f"receiver wants {sample_rate} Hz, {channels} ch, {sample_size * 8}-bit audio"
            )
        return source
    return await _original_open_source(source, sample_rate, channels, sample_size)


def install_hook() -> None:
    """Let pyatv's stream_file take a LivePcmSource. Safe to call more than once."""
    if getattr(raop, "open_source") is not _open_source:  # noqa: B009
        setattr(raop, "open_source", _open_source)  # noqa: B010


class PyatvAudioSink:
    def __init__(self, atv: AppleTV) -> None:
        self._atv = atv

    async def play(self, buffer: PcmBuffer, *, title: str, artist: str) -> None:
        install_hook()
        source = LivePcmSource(buffer, MediaMetadata(title=title, artist=artist))
        await self._atv.stream.stream_file(source)  # type: ignore[arg-type]

    async def set_volume(self, level: float) -> None:
        await self._atv.audio.set_volume(level)
