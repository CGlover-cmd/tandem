"""Runs system-audio streams: one shared capture, one buffer and sender per output.

A stream that fails while its device is still wanted waits and resumes: straight away when
the connection comes back (the session reconnects on its own), or after a backoff when the
connection stayed up but the stream itself broke. So a Wi-Fi blip costs a gap, not the stream.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field

from tandem.engine.audio import (
    FRAME_BYTES,
    AudioError,
    AudioSink,
    AudioStats,
    AudioStreamChanged,
    PcmBuffer,
    PcmCapture,
    StreamState,
    frames_to_seconds,
)
from tandem.engine.backoff import Backoff
from tandem.engine.events import EventBus
from tandem.engine.session import ConnectionState, ConnectionStateChanged, Link, Sleep

_LOGGER = logging.getLogger(__name__)

SinkFactory = Callable[[Link], AudioSink | None]
LinkLookup = Callable[[str], Link | None]


@dataclass
class _Output:
    buffer: PcmBuffer
    volume: float | None
    task: asyncio.Task[None] | None = None
    failures: int = 0
    # Totals from earlier buffers, before a restart.
    sent_frames: int = 0
    dropped_frames: int = 0
    silent_frames: int = 0
    underruns: int = 0
    retry: asyncio.TimerHandle | None = field(default=None, repr=False)


class AudioHub:
    def __init__(
        self,
        bus: EventBus,
        capture: Callable[[], PcmCapture],
        sink: SinkFactory,
        link: LinkLookup,
        *,
        title: str = "This PC",
        artist: str = "Tandem",
        backoff: Backoff | None = None,
        sleep: Sleep = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self._bus = bus
        self._capture_factory = capture
        self._sink_factory = sink
        self._link = link
        self._title = title
        self._artist = artist
        self._backoff = backoff or Backoff(initial=1.0, maximum=15.0)
        self._sleep = sleep
        self._rng = rng
        self._outputs: dict[str, _Output] = {}
        self._buffers: tuple[PcmBuffer, ...] = ()  # read from the capture thread
        self._capture: PcmCapture | None = None
        bus.subscribe(ConnectionStateChanged, self._on_state)

    # --- public --------------------------------------------------------------------

    def streaming(self, device_id: str) -> bool:
        return device_id in self._outputs

    def start(self, device_id: str, *, volume: float | None = None) -> None:
        """Start streaming to a connected device. Idempotent."""
        if device_id in self._outputs:
            return
        if self._link(device_id) is None:
            raise AudioError("not connected")
        output = _Output(self._new_buffer(), volume)
        self._outputs[device_id] = output
        self._refresh_buffers()
        self._ensure_capture()
        self._launch(device_id, output)

    async def stop(self, device_id: str, *, state: StreamState = StreamState.STOPPED) -> None:
        output = self._outputs.pop(device_id, None)
        if output is None:
            return
        self._refresh_buffers()
        await self._halt(output)
        if not self._outputs:
            self._stop_capture()
        self._publish(device_id, state)

    async def close(self) -> None:
        for device_id in list(self._outputs):
            await self.stop(device_id)

    def stats(self, device_id: str) -> AudioStats | None:
        output = self._outputs.get(device_id)
        if output is None:
            return None
        buffer = output.buffer
        return AudioStats(
            sent_seconds=frames_to_seconds(output.sent_frames + buffer.sent_frames),
            dropped_seconds=frames_to_seconds(output.dropped_frames + buffer.dropped_frames),
            silence_seconds=frames_to_seconds(output.silent_frames + buffer.silent_frames),
            buffered_ms=frames_to_seconds(buffer.buffered_frames) * 1000,
            underruns=output.underruns + buffer.underruns,
        )

    # --- internals -----------------------------------------------------------------

    def _new_buffer(self) -> PcmBuffer:
        return PcmBuffer()

    def _refresh_buffers(self) -> None:
        self._buffers = tuple(o.buffer for o in self._outputs.values())

    def _fan_out(self, data: bytes) -> None:
        # Capture thread: whole frames only, to every output's buffer.
        if len(data) % FRAME_BYTES:
            data = data[: len(data) - len(data) % FRAME_BYTES]
        for buffer in self._buffers:
            buffer.push(data)

    def _ensure_capture(self) -> None:
        if self._capture is None:
            capture = self._capture_factory()
            capture.start(self._fan_out)
            self._capture = capture

    def _stop_capture(self) -> None:
        capture, self._capture = self._capture, None
        if capture is not None:
            with suppress(Exception):
                capture.stop()

    async def _halt(self, output: _Output) -> None:
        if output.retry is not None:
            output.retry.cancel()
            output.retry = None
        output.buffer.close()
        task, output.task = output.task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task

    def _publish(self, device_id: str, state: StreamState, reason: str | None = None) -> None:
        self._bus.publish(AudioStreamChanged(device_id, state, reason))

    def _launch(self, device_id: str, output: _Output) -> None:
        if output.task is not None and not output.task.done():
            return
        link = self._link(device_id)
        if link is None:
            self._publish(device_id, StreamState.WAITING, "NotConnected")
            return
        sink = self._sink_factory(link)
        if sink is None:
            self._outputs.pop(device_id, None)
            self._refresh_buffers()
            if not self._outputs:
                self._stop_capture()
            self._publish(device_id, StreamState.FAILED, "NoAudioOutput")
            return
        # Fresh buffer per attempt, so a restart never plays stale audio.
        old = output.buffer
        output.sent_frames += old.sent_frames
        output.dropped_frames += old.dropped_frames
        output.silent_frames += old.silent_frames
        output.underruns += old.underruns
        old.close()
        output.buffer = self._new_buffer()
        self._refresh_buffers()
        output.task = asyncio.get_running_loop().create_task(
            self._run(device_id, output, sink), name="audio-stream"
        )

    async def _run(self, device_id: str, output: _Output, sink: AudioSink) -> None:
        self._publish(device_id, StreamState.STARTING)
        try:
            if output.volume is not None:
                await sink.set_volume(output.volume)
            self._publish(device_id, StreamState.STREAMING)
            await sink.play(output.buffer, title=self._title, artist=self._artist)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._outputs.get(device_id) is not output:
                return
            reason = type(exc).__name__
            _LOGGER.info("Audio stream to %s stopped (%s)", device_id, reason)
            self._publish(device_id, StreamState.WAITING, reason)
            output.task = None
            self._schedule_retry(device_id, output)
            return
        output.failures = 0
        if self._outputs.get(device_id) is output:
            output.task = None  # the sink ended on its own; leave it stopped

    def _schedule_retry(self, device_id: str, output: _Output) -> None:
        delay = self._backoff.delay(output.failures, self._rng)
        output.failures += 1
        loop = asyncio.get_running_loop()

        def retry() -> None:
            output.retry = None
            if self._outputs.get(device_id) is output and self._link(device_id) is not None:
                self._launch(device_id, output)

        output.retry = loop.call_later(delay, retry)

    def _on_state(self, event: ConnectionStateChanged) -> None:
        output = self._outputs.get(event.device_id)
        if output is None:
            return
        if event.state is ConnectionState.CONNECTED:
            if output.retry is not None:
                output.retry.cancel()
                output.retry = None
            self._launch(event.device_id, output)
        elif event.state is ConnectionState.WAITING:
            # The connection dropped. Don't wait for the sender to notice: stop it now and
            # start a fresh stream when the session reconnects.
            task, output.task = output.task, None
            if task is not None and not task.done():
                task.cancel()
                self._publish(event.device_id, StreamState.WAITING, event.reason)
        elif event.state in (ConnectionState.DISCONNECTED, ConnectionState.FAILED):
            # The user disconnected, or the session gave up: the stream ends with it.
            state = StreamState.STOPPED
            if event.state is ConnectionState.FAILED:
                state = StreamState.FAILED
            asyncio.get_running_loop().create_task(self.stop(event.device_id, state=state))
