"""PTP timing through the engine (ADR-0022): the shared timeline, timed senders, the sink."""

from __future__ import annotations

import asyncio
import struct
from types import SimpleNamespace
from typing import Any

import pytest
from pyatv.const import Protocol

from conftest import FakeCapture
from tandem.engine.adapters import ptp, pyatv_audio, pyatv_ptp
from tandem.engine.adapters.pyatv_adapter import PyatvBackend, PyatvLink
from tandem.engine.adapters.pyatv_audio import PyatvAudioSink, TimedPcmSource
from tandem.engine.audio import FRAME_BYTES, PcmBuffer
from tandem.engine.audio_hub import LOCAL_PREFIX, AudioHub
from tandem.engine.events import EventBus
from tandem.engine.timeline import NS, CaptureTimeline, frames_ns

PTP_FEATURES = {"features": "0x4A7FCA00,0x3C356BD0"}
OLD_FEATURES = {"features": "0x5A7FFFF7,0x1E"}
ADDRESS = "192.0.2.20"


def frames(n: int, value: int = 1000) -> bytes:
    return struct.pack("<hh", value, value) * n


# --- PcmBuffer -----------------------------------------------------------------------------


async def test_timed_buffer_ignores_pushes_and_counts_what_was_sent() -> None:
    buffer = PcmBuffer(prime_seconds=0.0)
    buffer.timed = True
    buffer.push(frames(500))
    assert buffer.buffered_frames == 0
    buffer.note_timed(352, 100)
    assert (buffer.sent_frames, buffer.silent_frames) == (252, 100)


# --- AudioHub ------------------------------------------------------------------------------


class _TimedSink:
    """A sender that reads by time, the way TimedPcmSource does (no pacing)."""

    def __init__(self) -> None:
        self.buffer: PcmBuffer | None = None
        self.started = asyncio.Event()

    async def set_volume(self, level: float) -> None:
        pass

    async def play(self, buffer: PcmBuffer, *, title: str, artist: str) -> None:
        buffer.timed = True
        self.buffer = buffer
        self.started.set()
        await asyncio.Event().wait()


async def _probe_sleep(_seconds: float) -> None:
    await asyncio.sleep(0)


def _hub(capture: FakeCapture, sinks: dict[str, Any]) -> AudioHub:
    return AudioHub(
        EventBus(),
        lambda: capture,
        lambda _link: None,
        lambda _id: None,
        sleep=_probe_sleep,
        local_sink=lambda output_id: sinks.get(output_id),
    )


async def test_hub_feeds_one_timeline_and_skips_timed_buffers() -> None:
    capture = FakeCapture()
    timed, plain = _TimedSink(), _TimedSink()
    hub = _hub(capture, {LOCAL_PREFIX + "a": timed})
    hub.start(LOCAL_PREFIX + "a", delay_ms=150)
    await timed.started.wait()
    buffer = timed.buffer
    assert buffer is not None
    assert buffer.timeline is not None
    assert buffer.offset_seconds == pytest.approx(0.15)
    capture.feed(frames(441))
    assert buffer.timeline.latest_ns is not None  # the shared timeline got it
    assert buffer.buffered_frames == 0  # the timed buffer didn't
    hub.set_delay(LOCAL_PREFIX + "a", 300)
    assert buffer.offset_seconds == pytest.approx(0.3)
    await hub.close()
    assert buffer.timeline.latest_ns is None  # cleared with the capture
    del plain


async def test_probe_on_a_timed_output_uses_its_own_timeline() -> None:
    capture = FakeCapture()
    timed = _TimedSink()
    hub = _hub(capture, {LOCAL_PREFIX + "a": timed})
    hub.start(LOCAL_PREFIX + "a")
    await timed.started.wait()
    buffer = timed.buffer
    assert buffer is not None
    shared = buffer.timeline
    seen: list[CaptureTimeline | None] = []

    async def watch() -> None:
        while not seen or seen[-1] is shared:
            seen.append(buffer.timeline)
            await asyncio.sleep(0)

    watcher = asyncio.create_task(watch())
    ahead = await hub.probe(LOCAL_PREFIX + "a", [frames(441), frames(441)], 10)
    await asyncio.wait_for(watcher, 1)
    assert ahead == 0.0  # nothing queued ahead of a timed probe
    probe_timeline = seen[-1]
    assert probe_timeline is not shared
    assert probe_timeline is not None
    assert probe_timeline.latest_ns is not None
    assert buffer.timeline is shared  # put back afterwards
    await hub.close()


async def test_probe_on_a_queued_output_still_queues() -> None:
    capture = FakeCapture()
    sink = _TimedSink()

    async def plain_play(buffer: PcmBuffer, *, title: str, artist: str) -> None:
        sink.buffer = buffer
        sink.started.set()
        await asyncio.Event().wait()

    sink.play = plain_play  # type: ignore[method-assign]
    hub = _hub(capture, {LOCAL_PREFIX + "b": sink})
    hub.start(LOCAL_PREFIX + "b")
    await sink.started.wait()
    assert sink.buffer is not None
    await hub.probe(LOCAL_PREFIX + "b", [frames(441)], 10)
    assert sink.buffer.buffered_frames == 441
    await hub.close()


# --- TimedPcmSource ------------------------------------------------------------------------


def _anchored(t0_ns: int) -> pyatv_ptp.PtpTimeline:
    timeline = pyatv_ptp.PtpTimeline()
    timeline.anchor(1000, t0_ns)
    return timeline


async def test_timed_source_reads_the_audio_captured_latency_before_play() -> None:
    capture_timeline = CaptureTimeline()
    # One second of audio whose sample value is its frame number (mod 30000).
    captured = b"".join(struct.pack("<hh", n % 30000, n % 30000) for n in range(44_100))
    capture_timeline.push(captured, 11 * NS)  # captured from 10 s to 11 s
    buffer = PcmBuffer()
    buffer.timeline = capture_timeline
    buffer.offset_seconds = 0.1
    # Plays from 12.5 s; latency 2.15 s and offset 0.1 s: wants audio from 10.25 s on.
    source = TimedPcmSource(buffer, pyatv_audio.MediaMetadata(), _anchored(12_500_000_000))
    assert buffer.timed
    data = await source.readframes(352)
    first = struct.unpack_from(">h", data, 0)[0]  # sent big-endian
    assert first == round(0.25 * 44_100)
    data = await source.readframes(352)
    assert struct.unpack_from(">h", data, 0)[0] == first + 352
    assert buffer.sent_frames == 704
    buffer.close()
    assert await source.readframes(352) == b""


async def test_timed_source_sends_silence_until_anchored() -> None:
    buffer = PcmBuffer()
    buffer.timeline = CaptureTimeline()
    source = TimedPcmSource(buffer, pyatv_audio.MediaMetadata(), pyatv_ptp.PtpTimeline())
    assert await source.readframes(352) == bytes(352 * FRAME_BYTES)
    assert buffer.silent_frames == 352


async def test_timed_source_passes_the_open_source_hook() -> None:
    import pyatv.protocols.raop as raop

    pyatv_audio.install_hook()
    buffer = PcmBuffer()
    source = TimedPcmSource(buffer, pyatv_audio.MediaMetadata(), pyatv_ptp.PtpTimeline())
    assert await getattr(raop, "open_source")(source, 44100, 2, 2) is source  # noqa: B009


def test_latency_leaves_room_for_the_capture() -> None:
    assert pyatv_audio.PTP_LATENCY_SECONDS > pyatv_audio.PTP_LEAD_SECONDS
    assert frames_ns(352) < (pyatv_audio.PTP_LATENCY_SECONDS - pyatv_audio.PTP_LEAD_SECONDS) * NS


# --- PyatvAudioSink ------------------------------------------------------------------------


class _Master:
    clock_id = 0xFFFF000000000001

    def add_peer(self, address: str) -> None:
        pass

    def remove_peer(self, address: str) -> None:
        pass


class _Share:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.acquired = 0
        self.released = 0

    async def acquire(self) -> Any:
        if self.error is not None:
            raise self.error
        self.acquired += 1
        return _Master()

    async def release(self) -> None:
        self.released += 1


class _Atv:
    def __init__(self, behaviour: str = "ok") -> None:
        self.sources: list[Any] = []
        self.registered: list[pyatv_ptp.PtpStream | None] = []
        behaviour_ = behaviour
        outer = self

        class Stream:
            async def stream_file(self, source: Any) -> None:
                outer.sources.append(source)
                stream = pyatv_ptp.stream_for(ADDRESS)
                outer.registered.append(stream)
                if behaviour_ == "setup-fails":
                    raise RuntimeError("receiver said no")
                if behaviour_ == "fails-later":
                    assert stream is not None
                    stream.sync_packets = 3
                    raise RuntimeError("dropped")

        class Audio:
            async def set_volume(self, level: float) -> None:
                pass

        self.stream = Stream()
        self.audio = Audio()


def _buffer() -> PcmBuffer:
    buffer = PcmBuffer()
    buffer.timeline = CaptureTimeline()
    return buffer


def _sink(atv: _Atv, share: _Share | None, refused: set[str], props: dict[str, str]) -> Any:
    return PyatvAudioSink(
        atv,  # type: ignore[arg-type]
        address=ADDRESS,
        properties=props,
        ptp=share,  # type: ignore[arg-type]
        ptp_refused=refused,
    )


async def test_sink_uses_ptp_for_a_ptp_receiver() -> None:
    atv, share, refused = _Atv(), _Share(), set[str]()
    buffer = _buffer()
    await _sink(atv, share, refused, PTP_FEATURES).play(buffer, title="T", artist="A")
    assert isinstance(atv.sources[0], TimedPcmSource)
    assert atv.registered[0] is not None
    assert pyatv_ptp.stream_for(ADDRESS) is None  # unregistered afterwards
    assert (share.acquired, share.released) == (1, 1)
    assert not buffer.timed  # handed back as a plain buffer
    assert not refused


async def test_sink_keeps_ntp_for_other_receivers() -> None:
    atv, share = _Atv(), _Share()
    await _sink(atv, share, set(), OLD_FEATURES).play(_buffer(), title="T", artist="A")
    assert type(atv.sources[0]) is pyatv_audio.LivePcmSource
    assert atv.registered == [None]
    assert share.acquired == 0


async def test_sink_without_a_timeline_or_clock_uses_ntp() -> None:
    atv = _Atv()
    await _sink(atv, None, set(), PTP_FEATURES).play(_buffer(), title="T", artist="A")
    atv2, share = _Atv(), _Share()
    await _sink(atv2, share, set(), PTP_FEATURES).play(PcmBuffer(), title="T", artist="A")
    assert type(atv.sources[0]) is pyatv_audio.LivePcmSource
    assert type(atv2.sources[0]) is pyatv_audio.LivePcmSource


async def test_sink_falls_back_when_the_clock_cant_start() -> None:
    atv, share = _Atv(), _Share(ptp.PtpError("port 319 busy"))
    await _sink(atv, share, set(), PTP_FEATURES).play(_buffer(), title="T", artist="A")
    assert type(atv.sources[0]) is pyatv_audio.LivePcmSource


async def test_sink_remembers_a_receiver_that_refused_ptp() -> None:
    share, refused = _Share(), set[str]()
    with pytest.raises(RuntimeError):
        await _sink(_Atv("setup-fails"), share, refused, PTP_FEATURES).play(
            _buffer(), title="T", artist="A"
        )
    assert refused == {ADDRESS}
    assert share.released == 1
    # The retry streams with NTP timing.
    atv = _Atv()
    await _sink(atv, share, refused, PTP_FEATURES).play(_buffer(), title="T", artist="A")
    assert type(atv.sources[0]) is pyatv_audio.LivePcmSource


async def test_sink_doesnt_blame_ptp_for_a_later_drop() -> None:
    refused: set[str] = set()
    with pytest.raises(RuntimeError):
        await _sink(_Atv("fails-later"), _Share(), refused, PTP_FEATURES).play(
            _buffer(), title="T", artist="A"
        )
    assert not refused


# --- PtpClockShare -------------------------------------------------------------------------


class _FakeMaster:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1


async def test_clock_share_starts_once_and_stops_after_the_last() -> None:
    made: list[_FakeMaster] = []

    def factory() -> _FakeMaster:
        made.append(_FakeMaster())
        return made[-1]

    share = pyatv_ptp.PtpClockShare(factory)
    first = await share.acquire()
    second = await share.acquire()
    assert first is second
    assert len(made) == 1
    await share.release()
    assert made[0].stopped == 0
    await share.release()
    assert made[0].stopped == 1
    await share.release()  # extra release is harmless
    third = await share.acquire()
    assert third is not first
    await share.release()


# --- PyatvBackend --------------------------------------------------------------------------


def test_backend_gives_its_sinks_the_clock_and_the_receiver() -> None:
    raop = SimpleNamespace(properties=PTP_FEATURES)

    def get_service(protocol: Protocol) -> Any:
        return raop if protocol is Protocol.RAOP else None

    config = SimpleNamespace(address=ADDRESS, get_service=get_service)
    backend = PyatvBackend(storage=SimpleNamespace())  # type: ignore[arg-type]
    link = PyatvLink(_Atv(), None, config)  # type: ignore[arg-type]
    sink = backend.audio_sink(link)
    assert isinstance(sink, PyatvAudioSink)
    assert sink._address == ADDRESS  # pyright: ignore[reportPrivateUsage]
    assert sink._ptp is not None  # pyright: ignore[reportPrivateUsage]
    assert pyatv_ptp.supports_ptp(sink._properties)  # pyright: ignore[reportPrivateUsage]
    plain = PyatvBackend(storage=SimpleNamespace(), ptp_timing=False)  # type: ignore[arg-type]
    sink = plain.audio_sink(PyatvLink(_Atv(), None))  # type: ignore[arg-type]
    assert isinstance(sink, PyatvAudioSink)
    assert sink._ptp is None  # pyright: ignore[reportPrivateUsage]
    assert sink._address is None  # pyright: ignore[reportPrivateUsage]
