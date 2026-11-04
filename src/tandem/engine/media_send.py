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
    """The media can't be sent. `str()` is safe to show."""


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
