"""What the PC is playing, from Windows' media controls (Phase 6, ADR-0013; Music spike 1).

Spotify, Apple Music, browsers and most players report to Windows' system media transport
controls (GSMTC). Tandem reads the current session and can play, pause and skip it, which makes
the Music tab a remote for the official apps while their sound goes out through the router.
The Windows side is an adapter (`adapters/media_sessions.py`); this module polls it.

Titles and artists are personal: shown in the window, never logged.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from tandem.engine.events import Event, EventBus

_LOGGER = logging.getLogger(__name__)


class PcMediaCommand(Enum):
    PLAY_PAUSE = "play_pause"
    NEXT = "next"
    PREVIOUS = "previous"


@dataclass(frozen=True, slots=True)
class PcNowPlaying:
    state: str = "other"  # playing, paused, stopped, other
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    app: str | None = None
    """A friendly app name (Spotify, Apple Music, a browser)."""
    can_play_pause: bool = False
    can_next: bool = False
    can_previous: bool = False


@dataclass(frozen=True, slots=True)
class PcNowPlayingChanged(Event):
    now_playing: PcNowPlaying | None = None


class MediaSessions(Protocol):
    async def current(self) -> PcNowPlaying | None:
        """The session Windows considers current, or None when nothing reports."""
        ...

    async def command(self, command: PcMediaCommand) -> bool:
        """Send a command to the current session. False if there is none or it refused."""
        ...


class PcMediaWatcher:
    def __init__(self, bus: EventBus, sessions: MediaSessions, *, interval: float = 1.0) -> None:
        self._bus = bus
        self._sessions = sessions
        self._interval = interval
        self._task: asyncio.Task[None] | None = None
        self.now_playing: PcNowPlaying | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run(), name="pc-media")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def refresh(self) -> None:
        try:
            current = await self._sessions.current()
        except Exception as exc:  # Windows' media service can be busy or missing
            _LOGGER.debug("Reading the PC's media session failed (%s)", type(exc).__name__)
            current = None
        if current != self.now_playing:
            self.now_playing = current
            self._bus.publish(PcNowPlayingChanged(current))

    async def command(self, command: PcMediaCommand) -> bool:
        try:
            done = await self._sessions.command(command)
        except Exception as exc:
            _LOGGER.info("A PC media command failed (%s)", type(exc).__name__)
            return False
        await self.refresh()
        return done

    async def _run(self) -> None:
        while True:
            await self.refresh()
            await asyncio.sleep(self._interval)


class NoMediaSessions:
    """For PCs (and tests) without Windows' media controls."""

    async def current(self) -> PcNowPlaying | None:
        return None

    async def command(self, command: PcMediaCommand) -> bool:
        return False


def friendly_app(app_id: str | None) -> str | None:
    """A readable name from a session's app id (an AppUserModelID or an exe name)."""
    if not app_id:
        return None
    lowered = app_id.lower()
    known = (
        ("spotify", "Spotify"),
        ("applemusic", "Apple Music"),
        ("itunes", "iTunes"),
        ("msedge", "Microsoft Edge"),
        ("chrome", "Google Chrome"),
        ("firefox", "Firefox"),
        ("zunemusic", "Media Player"),
        ("vlc", "VLC"),
    )
    for needle, name in known:
        if needle in lowered:
            return name
    base = app_id.split("!")[0].rsplit("\\", 1)[-1]
    if base.lower().endswith(".exe"):
        base = base[:-4]
    if "." in base and "_" in base:  # Package.Name_publisherhash
        base = base.split("_")[0].split(".")[-1]
    return base or None
