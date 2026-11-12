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
import logging
import sys
import uuid
from collections.abc import Mapping
from typing import Any

import pyatv.protocols.raop as raop
from pyatv.interface import AppleTV, MediaMetadata
from pyatv.protocols.raop.audio_source import AudioSource

from tandem.engine.adapters import ptp, pyatv_ptp
from tandem.engine.audio import (
    CHANNELS,
    FRAME_BYTES,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    AudioError,
    PcmBuffer,
)
from tandem.engine.timeline import NS

_LOGGER = logging.getLogger(__name__)


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


# PTP timing (ADR-0022). A packet's play time is set `PTP_LEAD` after its stream starts; the
# audio in it was captured `PTP_LATENCY` before it plays. The gap between the two is the time
# the capture has to deliver a block before it is sent.
PTP_LEAD_SECONDS = 2.0
PTP_LATENCY_SECONDS = PTP_LEAD_SECONDS + 0.15
_PTP_GROUP = str(uuid.uuid4()).upper()  # every output of this run is one AirPlay group


class TimedPcmSource(LivePcmSource):
    """Reads the shared source by time: frame k carries the audio captured `latency` before
    `timeline.play_ns(k)`, plus the output's own line-up offset."""

    def __init__(
        self,
        buffer: PcmBuffer,
        metadata: MediaMetadata,
        timeline: pyatv_ptp.PtpTimeline,
        latency_seconds: float = PTP_LATENCY_SECONDS,
    ) -> None:
        super().__init__(buffer, metadata)
        buffer.timed = True
        self._timeline = timeline
        self._latency_ns = int(latency_seconds * NS)
        self._sent = 0

    async def readframes(self, nframes: int) -> bytes:
        buffer = self._buffer
        if buffer.closed:
            return b""
        source = buffer.timeline
        if source is None or not self._timeline.anchored:
            buffer.note_timed(nframes, nframes)
            return bytes(nframes * FRAME_BYTES)
        wanted = (
            self._timeline.play_ns(self._sent) - self._latency_ns - int(buffer.offset_seconds * NS)
        )
        data, silent = source.read_at(wanted, nframes)
        self._sent += nframes
        buffer.note_timed(nframes, silent)
        return to_network_order(data)


class PyatvAudioSink:
    """Streams to one AirPlay receiver. With `ptp` (the shared clock), a receiver that
    advertises PTP is streamed on PTP timing from the shared timeline; if its PTP setup
    fails, it is remembered in `ptp_refused` and the next attempt uses pyatv's NTP timing."""

    def __init__(
        self,
        atv: AppleTV,
        *,
        address: str | None = None,
        properties: Mapping[str, str] | None = None,
        ptp: pyatv_ptp.PtpClockShare | None = None,
        ptp_refused: set[str] | None = None,
    ) -> None:
        self._atv = atv
        self._address = address
        self._properties = dict(properties or {})
        self._ptp = ptp
        self._refused = ptp_refused if ptp_refused is not None else set()

    def _wants_ptp(self, buffer: PcmBuffer) -> bool:
        return (
            self._ptp is not None
            and self._address is not None
            and self._address not in self._refused
            and buffer.timeline is not None
            and pyatv_ptp.supports_ptp(self._properties)
        )

    async def play(self, buffer: PcmBuffer, *, title: str, artist: str) -> None:
        install_hook()
        metadata = MediaMetadata(title=title, artist=artist)
        if self._wants_ptp(buffer):
            assert self._ptp is not None
            assert self._address is not None
            try:
                master = await self._ptp.acquire()
            except ptp.PtpError as exc:
                _LOGGER.info("PTP clock unavailable, using NTP timing (%s)", exc)
            else:
                await self._play_ptp(buffer, metadata, master, self._address, self._ptp)
                return
        source = LivePcmSource(buffer, metadata)
        await self._atv.stream.stream_file(source)  # type: ignore[arg-type]

    async def _play_ptp(
        self,
        buffer: PcmBuffer,
        metadata: MediaMetadata,
        master: ptp.PtpMaster,
        address: str,
        share: pyatv_ptp.PtpClockShare,
    ) -> None:
        stream = pyatv_ptp.PtpStream(master, _PTP_GROUP, int(PTP_LEAD_SECONDS * NS))
        pyatv_ptp.register(address, stream)
        try:
            source = TimedPcmSource(buffer, metadata, stream.timeline)
            await self._atv.stream.stream_file(source)  # type: ignore[arg-type]
        except Exception:
            if stream.sync_packets == 0:
                # It failed while setting up: likely the receiver won't take our clock.
                _LOGGER.info("PTP setup failed; this receiver gets NTP timing next time")
                self._refused.add(address)
            raise
        finally:
            buffer.timed = False
            pyatv_ptp.unregister(address)
            await share.release()

    async def set_volume(self, level: float) -> None:
        await self._atv.audio.set_volume(level)
