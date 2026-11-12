"""Send a video file or a link to an Apple TV (Phase 7, ADR-0015).

The Apple TV plays a URL itself. For a link, that's the link; for a file on this PC, Tandem
shares just that file from a small web server on the home network, under a random path that
changes for every file, and hands the TV that address. Nothing else on the PC is reachable.
FairPlay-free: this is AirPlay's "play this URL", not mirroring (ADR-0006).

File paths and links are personal: never logged.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import socket
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

from tandem.engine.events import Event

_LOGGER = logging.getLogger(__name__)

VIDEO_SUFFIXES = (".mp4", ".m4v", ".mov", ".mp3", ".m4a", ".aac", ".wav")
"""What an Apple TV plays from a URL (H.264/HEVC in MP4 or QuickTime, and common audio)."""


class MediaError(Exception):
    """The media can't be sent. `str()` is safe to show; `reason` says why, as a code."""

    NOT_A_TV = "not_a_tv"
    FILE_GONE = "file_gone"
    NOT_PLAYABLE = "not_playable"  # a format or codec the Apple TV can't play

    def __init__(self, message: str, reason: str = "") -> None:
        super().__init__(message)
        self.reason = reason


class SendState(Enum):
    STARTING = "starting"
    PLAYING = "playing"
    ENDED = "ended"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MediaSendChanged(Event):
    device_id: str
    state: SendState
    title: str | None = None
    """The file name or link host; personal, never logged."""
    reason: str | None = None


class MediaSender(Protocol):
    async def play_url(self, url: str) -> None:
        """Play the URL on the device. Returns when playback ends; raises if it can't play."""
        ...


# Sample entries (codecs) in an MP4 or QuickTime file that an Apple TV won't play from a URL.
# "hev1" is HEVC tagged the way Apple's players refuse; the same video tagged "hvc1" plays.
_UNPLAYABLE_CODECS = frozenset({b"vp08", b"vp09", b"av01", b"hev1", b"dvhe", b"opus", b"fLaC"})
_CONTAINERS = frozenset({b"moov", b"trak", b"mdia", b"minf", b"stbl"})
_MAX_BOXES = 10_000


def check_playable(path: Path) -> None:
    """Raise `MediaError(NOT_PLAYABLE)` for a file the Apple TV won't play, before it's sent.

    By file type first (MKV, AVI, WebM, WMV never play), then, for MP4 and QuickTime files, by
    the codecs inside (VP9, AV1 and "hev1"-tagged HEVC don't). A file it can't read is let
    through: the Apple TV has the last word. AirParrot 3 converts more formats itself; Tandem
    says why instead, which needs no converter in the app.
    """
    if path.suffix.lower() not in VIDEO_SUFFIXES:
        raise MediaError("The Apple TV can't play this kind of file.", MediaError.NOT_PLAYABLE)
    if path.suffix.lower() not in (".mp4", ".m4v", ".mov", ".m4a"):
        return
    try:
        codecs = mp4_codecs(path)
    except OSError:
        return
    if codecs & _UNPLAYABLE_CODECS:
        raise MediaError("The Apple TV can't play the video in this file.", MediaError.NOT_PLAYABLE)


def mp4_codecs(path: Path) -> frozenset[bytes]:
    """The four-letter codec codes of every track in an MP4 or QuickTime file ("avc1",
    "hvc1", "mp4a" ...). Reads box headers only, so it's quick on a large file."""
    found: set[bytes] = set()
    with path.open("rb") as handle:
        handle.seek(0, 2)
        _walk(handle, 0, handle.tell(), found, [0])
    return frozenset(found)


def _walk(handle: Any, start: int, end: int, found: set[bytes], count: list[int]) -> None:
    offset = start
    while offset + 8 <= end:
        count[0] += 1
        if count[0] > _MAX_BOXES:
            return
        handle.seek(offset)
        header = handle.read(8)
        if len(header) < 8:
            return
        size, kind = int.from_bytes(header[:4], "big"), header[4:8]
        body = offset + 8
        if size == 1:
            large = handle.read(8)
            if len(large) < 8:
                return
            size, body = int.from_bytes(large, "big"), offset + 16
        elif size == 0:
            size = end - offset
        if size < body - offset or offset + size > end:
            return
        if kind in _CONTAINERS:
            _walk(handle, body, offset + size, found, count)
        elif kind == b"stsd":
            _sample_entries(handle, body, offset + size, found)
        offset += size


def _sample_entries(handle: Any, start: int, end: int, found: set[bytes]) -> None:
    handle.seek(start)
    head = handle.read(8)  # version and flags, then the entry count
    if len(head) < 8:
        return
    entries = int.from_bytes(head[4:8], "big")
    offset = start + 8
    for _ in range(min(entries, 16)):
        handle.seek(offset)
        entry = handle.read(8)
        if len(entry) < 8:
            return
        size = int.from_bytes(entry[:4], "big")
        found.add(entry[4:8])
        if size < 8 or offset + size > end:
            return
        offset += size


def is_link(location: str) -> bool:
    return urlsplit(location.strip()).scheme in ("http", "https")


def title_for(location: str) -> str:
    if is_link(location):
        parts = urlsplit(location.strip())
        name = parts.path.rstrip("/").rsplit("/", 1)[-1]
        return name or parts.hostname or "Link"
    return Path(location).name


def local_address_towards(address: str) -> str:
    """This PC's address on the network that reaches `address` (no packet is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((address, 7000))
        return str(probe.getsockname()[0])


class MediaServer:
    """Serves shared files over HTTP, one random path per file."""

    def __init__(self, *, host: str = "0.0.0.0", port: int = 0) -> None:
        self._host = host
        self._port = port
        self._files: dict[str, Path] = {}
        self._runner: Any = None
        self.port = 0

    @property
    def running(self) -> bool:
        return self._runner is not None

    async def start(self) -> None:
        if self._runner is not None:
            return
        from aiohttp import web

        app = web.Application()
        app.router.add_get("/media/{token}/{name}", self._serve)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._port)
        await site.start()
        address: Any = runner.addresses[0]
        self.port = int(address[1])
        self._runner = runner

    async def stop(self) -> None:
        runner, self._runner = self._runner, None
        if runner is not None:
            await runner.cleanup()
        self._files.clear()

    def share(self, path: Path) -> str:
        """The URL path for one file. Earlier files stay shared until the server stops."""
        token = secrets.token_urlsafe(18)
        self._files[token] = path
        return f"/media/{token}/{quote(path.name)}"

    async def _serve(self, request: Any) -> Any:
        from aiohttp import web

        path = self._files.get(request.match_info["token"])
        if path is None or not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)


class MediaSends:
    """One playback per device; a new send replaces the last one."""

    def __init__(self, publish: Any) -> None:
        self._publish = publish
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def playing(self, device_id: str) -> bool:
        task = self._tasks.get(device_id)
        return task is not None and not task.done()

    async def start(self, device_id: str, sender: MediaSender, url: str, title: str) -> None:
        await self.stop(device_id)
        self._publish(MediaSendChanged(device_id, SendState.STARTING, title))
        self._tasks[device_id] = asyncio.get_running_loop().create_task(
            self._run(device_id, sender, url, title), name="media-send"
        )

    async def stop(self, device_id: str) -> None:
        task = self._tasks.pop(device_id, None)
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task

    async def close(self) -> None:
        for device_id in list(self._tasks):
            await self.stop(device_id)

    async def _run(self, device_id: str, sender: MediaSender, url: str, title: str) -> None:
        self._publish(MediaSendChanged(device_id, SendState.PLAYING, title))
        try:
            await sender.play_url(url)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            reason = type(exc).__name__
            _LOGGER.info("Sending media stopped (%s)", reason)
            self._publish(MediaSendChanged(device_id, SendState.FAILED, title, reason))
            return
        self._publish(MediaSendChanged(device_id, SendState.ENDED, title))
