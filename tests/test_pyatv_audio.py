from __future__ import annotations

import io
import struct
import sys
from typing import Any

import pyatv.protocols.raop as raop
import pytest
from pyatv.interface import MediaMetadata

from tandem.engine.adapters import loopback, pyatv_audio
from tandem.engine.adapters.pyatv_audio import LivePcmSource, PyatvAudioSink, install_hook
from tandem.engine.audio import AudioError, PcmBuffer


async def _open_source(source: Any, *args: int) -> Any:
    """Call through the module attribute, the way stream_file does."""
    return await getattr(raop, "open_source")(source, *args)  # noqa: B009


def test_hook_point_still_exists() -> None:
    # stream_file looks up open_source in this module; if pyatv moves it, the hook breaks.
    assert callable(getattr(raop, "open_source", None))


async def test_live_source_passes_through_the_hook() -> None:
    install_hook()
    install_hook()  # twice is harmless
    buffer = PcmBuffer(prime_seconds=0.0)
    buffer.push(struct.pack("<hh", 5, 5) * 352)
    source = LivePcmSource(buffer, MediaMetadata(title="This PC", artist="Tandem"))
    opened = await _open_source(source, 44100, 2, 2)
    assert opened is source
    assert (source.sample_rate, source.channels, source.sample_size, source.duration) == (
        44100,
        2,
        2,
        0,
    )
    assert await source.readframes(352) == struct.pack(">hh", 5, 5) * 352  # big-endian
    assert (await source.get_metadata()).title == "This PC"
    await source.close()
    assert buffer.closed


async def test_hook_rejects_other_formats() -> None:
    install_hook()
    source = LivePcmSource(PcmBuffer(), MediaMetadata())
    with pytest.raises(AudioError, match="48000 Hz"):
        await _open_source(source, 48000, 2, 2)


async def test_hook_leaves_other_sources_to_pyatv(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []

    async def original(source: Any, *args: Any) -> str:
        seen.append(source)
        return "pyatv's own source"

    monkeypatch.setattr(pyatv_audio, "_original_open_source", original)
    install_hook()
    stream = io.BytesIO(b"")
    assert await _open_source(stream, 44100, 2, 2) == "pyatv's own source"
    assert seen == [stream]


async def test_sink_streams_through_pyatv() -> None:
    calls: list[Any] = []

    class Stream:
        async def stream_file(self, source: Any) -> None:
            calls.append(("stream", type(source).__name__, (await source.get_metadata()).artist))

    class Audio:
        async def set_volume(self, level: float) -> None:
            calls.append(("volume", level))

    class Atv:
        stream = Stream()
        audio = Audio()

    sink = PyatvAudioSink(Atv())  # type: ignore[arg-type]
    await sink.set_volume(30)
    await sink.play(PcmBuffer(), title="This PC", artist="Tandem")
    assert calls == [("volume", 30), ("stream", "LivePcmSource", "Tandem")]


def test_loopback_needs_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(AudioError, match="Windows"):
        loopback.LoopbackCapture().start(lambda _data: None)


def test_loopback_stop_without_start() -> None:
    loopback.LoopbackCapture().stop()


def test_network_order_swaps_each_sample() -> None:
    assert pyatv_audio.to_network_order(struct.pack("<hh", 1, -2)) == struct.pack(">hh", 1, -2)
    assert pyatv_audio.to_network_order(b"") == b""
