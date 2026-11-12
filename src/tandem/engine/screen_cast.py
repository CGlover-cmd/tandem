"""Cast the PC's screen to an Apple TV as a live video stream (ADR-0006 addendum, Spike I).

Not screen mirroring, and no FairPlay: the screen (and the PC's sound) is encoded as H.264 and
AAC into a live HLS playlist of short segments, in a temporary folder, which the media server
shares under a random path. The TV is then asked to play that address with the same "play this
URL" request Send to TV uses. The TV plays it like any video, so the picture runs a few
seconds behind the PC.

This module is protocol-agnostic: capturing and encoding are a `ScreenEncoder` from the
backend (dxcam and PyAV in `adapters/screen_capture.py`), and tests use fakes.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import tempfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from tandem.engine.audio import PcmCapture
from tandem.engine.events import Event
from tandem.engine.media_send import MediaSender

_LOGGER = logging.getLogger(__name__)

PLAYLIST = "index.m3u8"
SEGMENT_NAME = re.compile(r"^index\d{1,9}\.ts$")
"""The only file names a cast shares: the playlist and its numbered segments."""

SEGMENT_SECONDS = 1.0
LIST_SIZE = 6
"""Segments kept in the playlist (older ones are deleted): a sliding live window."""
READY_SEGMENTS = 3
"""Segments to have written before asking the TV to play: it starts three from the end."""
READY_TIMEOUT = 15.0


class CastQuality(Enum):
    LOW = "low"
    """720p, 4 Mbit/s: for a busy Wi-Fi network."""
    STANDARD = "standard"
    """1080p, 8 Mbit/s."""
    HIGH = "high"
    """1080p, 14 Mbit/s: sharper text and fast motion."""


@dataclass(frozen=True, slots=True)
class CastSettings:
    screen: int
    width: int
    height: int
    fps: int
    bitrate: int
    sound: bool = True
    segment_seconds: float = SEGMENT_SECONDS
    list_size: int = LIST_SIZE


PRESETS: dict[CastQuality, tuple[int, int, int, int]] = {
    CastQuality.LOW: (1280, 720, 30, 4_000_000),
    CastQuality.STANDARD: (1920, 1080, 30, 8_000_000),
    CastQuality.HIGH: (1920, 1080, 30, 14_000_000),
}
"""Width, height, frames per second and bit rate. 30 fps: Spike E found 1080p60 from Python
can't keep up once a 4K screen has to be scaled down on the CPU."""


def settings_for(quality: CastQuality, screen: int = 0, *, sound: bool = True) -> CastSettings:
    width, height, fps, bitrate = PRESETS[quality]
    return CastSettings(screen, width, height, fps, bitrate, sound)


@dataclass(frozen=True, slots=True)
class Screen:
    """One of the PC's displays. No names (a monitor's name can identify it): an index and
    its size only."""

    index: int
    width: int
    height: int
    primary: bool = False


class CastError(Exception):
    """The cast couldn't start. `reason` is a code; `str()` holds nothing private."""

    NOT_A_TV = "not_a_tv"
    NO_SCREEN = "no_screen"
    ENCODER = "encoder"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ScreenEncoder(Protocol):
    """Captures one screen (and the sound, if given a capture) into an HLS folder."""

    def start(self, folder: Path, settings: CastSettings, sound: PcmCapture | None) -> None:
        """Start capturing and writing `index.m3u8` and its segments. Raises `CastError`."""
        ...

    def stop(self) -> None:
        """Stop and finish the files. Safe to call twice."""
        ...

    @property
    def failed(self) -> bool:
        """The encoder stopped by itself (the screen went away, the encoder failed)."""
        ...


class CastState(Enum):
    STARTING = "starting"
    PLAYING = "playing"
    ENDED = "ended"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ScreenCastChanged(Event):
    device_id: str
    state: CastState
    reason: str | None = None
    """Why it failed: a `CastError` reason or an exception type name. Holds nothing private."""


def segments_listed(playlist: str) -> int:
    return playlist.count("#EXTINF")


def is_cast_file(name: str) -> bool:
    return name == PLAYLIST or SEGMENT_NAME.match(name) is not None


class CastFolder:
    """A temporary folder for one cast's playlist and segments, deleted afterwards."""

    def __init__(self, parent: Path | None = None) -> None:
        self.path = Path(tempfile.mkdtemp(prefix="tandem-cast-", dir=parent))

    def playlist(self) -> str | None:
        try:
            return (self.path / PLAYLIST).read_text(encoding="utf-8")
        except OSError:
            return None

    def remove(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


class FolderShare(Protocol):
    """Where a cast folder is served from (the engine's media server, already running)."""

    def share_folder(self, folder: Path, allow: Callable[[str], bool], entry: str) -> str:
        """The URL path of `entry` in the folder; only names `allow` accepts are served."""
        ...

    def unshare(self, path: str) -> None: ...


Sleep = Callable[[float], Any]


@dataclass(eq=False, slots=True)
class _Cast:
    """One running cast and what to tidy up when it ends."""

    device_id: str
    encoder: ScreenEncoder
    folder: CastFolder
    share: FolderShare
    path: str
    finished: bool = False


class ScreenCasts:
    """One cast at a time (there is one screen capture): starting another stops the first."""

    def __init__(
        self,
        publish: Callable[[Event], None],
        *,
        poll: float = 0.1,
        ready_timeout: float = READY_TIMEOUT,
        folder_parent: Path | None = None,
    ) -> None:
        self._publish = publish
        self._poll = poll
        self._ready_timeout = ready_timeout
        self._folder_parent = folder_parent
        self._task: asyncio.Task[None] | None = None
        self._cast: _Cast | None = None
        self._device_id: str | None = None

    @property
    def device_id(self) -> str | None:
        """The TV being cast to, while a cast starts or runs."""
        return self._device_id

    async def start(
        self,
        device_id: str,
        sender: MediaSender,
        encoder: ScreenEncoder,
        settings: CastSettings,
        share: FolderShare,
        base_url: str,
        sound: PcmCapture | None = None,
    ) -> None:
        """Start capturing, wait for the first segments, then ask the TV to play them.
        Returns once the TV has been asked; `ScreenCastChanged` reports the rest."""
        await self.stop()
        self._device_id = device_id
        self._publish(ScreenCastChanged(device_id, CastState.STARTING))
        folder = CastFolder(self._folder_parent)
        try:
            await asyncio.to_thread(encoder.start, folder.path, settings, sound)
            await self._wait_ready(folder, encoder)
        except BaseException as exc:
            await asyncio.to_thread(encoder.stop)
            folder.remove()
            reason = exc.reason if isinstance(exc, CastError) else type(exc).__name__
            self._device_id = None
            if not isinstance(exc, asyncio.CancelledError):
                _LOGGER.info("Casting the screen didn't start (%s)", reason)
                self._publish(ScreenCastChanged(device_id, CastState.FAILED, reason))
            raise
        path = share.share_folder(folder.path, is_cast_file, PLAYLIST)
        cast = _Cast(device_id, encoder, folder, share, path)
        self._cast = cast
        self._publish(ScreenCastChanged(device_id, CastState.PLAYING))
        self._task = asyncio.get_running_loop().create_task(
            self._run(cast, sender, base_url + path), name="screen-cast"
        )

    async def _wait_ready(self, folder: CastFolder, encoder: ScreenEncoder) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._ready_timeout
        while True:
            playlist = await asyncio.to_thread(folder.playlist)
            if playlist is not None and segments_listed(playlist) >= READY_SEGMENTS:
                return
            if encoder.failed or loop.time() > deadline:
                raise CastError(CastError.ENCODER)
            await asyncio.sleep(self._poll)

    async def _run(self, cast: _Cast, sender: MediaSender, url: str) -> None:
        play = asyncio.ensure_future(sender.play_url(url))
        watch = asyncio.ensure_future(self._watch(cast.encoder))
        state, reason = CastState.ENDED, None
        try:
            done, _ = await asyncio.wait({play, watch}, return_when=asyncio.FIRST_COMPLETED)
            if play in done and play.exception() is not None:
                state, reason = CastState.FAILED, type(play.exception()).__name__
            elif watch in done:
                state, reason = CastState.FAILED, CastError.ENCODER
        finally:
            for task in (play, watch):
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task
            await self._finish(cast, state, reason)

    async def _finish(self, cast: _Cast, state: CastState, reason: str | None) -> None:
        """Tidy up after a cast, once: stop sharing, stop the encoder, delete the folder."""
        if cast.finished:
            return
        cast.finished = True
        cast.share.unshare(cast.path)
        await asyncio.to_thread(cast.encoder.stop)
        await asyncio.to_thread(cast.folder.remove)
        if self._cast is cast:
            self._cast = None
            self._device_id = None
        if state is CastState.FAILED:
            _LOGGER.info("Casting the screen stopped (%s)", reason)
        self._publish(ScreenCastChanged(cast.device_id, state, reason))

    async def _watch(self, encoder: ScreenEncoder) -> None:
        # The encoder runs on its own thread and only sets a flag: polling it is simplest.
        while not encoder.failed:  # noqa: ASYNC110
            await asyncio.sleep(self._poll * 5)

    async def stop(self, device_id: str | None = None) -> None:
        """Stop the cast (only if it is to `device_id`, when given)."""
        task, cast = self._task, self._cast
        if task is None or cast is None or (device_id is not None and device_id != cast.device_id):
            return
        self._task = None
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        # A task cancelled before it first ran never reached its own clean-up.
        await self._finish(cast, CastState.ENDED, None)

    async def close(self) -> None:
        await self.stop()
