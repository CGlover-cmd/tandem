"""Decode music files and internet radio to PCM for the player (Phase 6), via miniaudio.

miniaudio decodes MP3, FLAC, WAV and Ogg Vorbis. Radio streams are read with its ICY client,
so MP3 and Ogg stations work; AAC-only stations don't (the player says the track failed).
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

from tandem.engine.audio import CHANNELS, SAMPLE_RATE
from tandem.engine.player import DecodedStream, Track, TrackKind

AUDIO_SUFFIXES = (".mp3", ".flac", ".wav", ".ogg", ".oga")


class _MiniaudioStream:  # pragma: no cover - thin wrapper over miniaudio; checked by hand
    def __init__(
        self,
        generator: Generator[Any, int, None],
        duration: float | None,
        close: Any,
        first: bytes = b"",
    ):
        self._generator = generator
        self._duration = duration
        self._close = close
        self._done = False
        self._first = first  # the chunk miniaudio hands back when the stream is primed

    @property
    def duration(self) -> float | None:
        return self._duration

    def read(self, frames: int) -> bytes:
        if self._first:
            first, self._first = self._first, b""
            return first
        if self._done:
            return b""
        try:
            samples = self._generator.send(frames)
        except StopIteration:
            self._done = True
            return b""
        return bytes(samples.tobytes())

    def close(self) -> None:
        self._generator.close()
        if self._close is not None:
            self._close()


def open_track(track: Track) -> DecodedStream:  # pragma: no cover - needs real files
    import miniaudio

    fmt = miniaudio.SampleFormat.SIGNED16
    if track.kind is TrackKind.FILE:
        path = Path(track.location)
        info: Any = miniaudio.get_file_info(str(path))
        generator: Any = miniaudio.stream_file(  # pyright: ignore[reportUnknownVariableType]
            str(path), output_format=fmt, nchannels=CHANNELS, sample_rate=SAMPLE_RATE
        )
        first = bytes(next(generator).tobytes())  # priming returns the first chunk: keep it
        return _MiniaudioStream(generator, float(info.duration), None, first)
    client: Any = miniaudio.IceCastClient(track.location)
    generator = miniaudio.stream_any(  # pyright: ignore[reportUnknownVariableType]
        client, output_format=fmt, nchannels=CHANNELS, sample_rate=SAMPLE_RATE
    )
    first = bytes(next(generator).tobytes())
    return _MiniaudioStream(generator, None, client.close, first)


def is_audio_file(path: str) -> bool:
    return path.lower().endswith(AUDIO_SUFFIXES)
