"""What the PC is playing, from Windows' media controls (Phase 6, ADR-0013; Music spike 1).

Spotify, Apple Music, browsers and most players report to Windows' system media transport
controls (GSMTC). Tandem reads the current session and can play, pause, skip and seek it, which
makes the Music tab a remote for the official apps while their sound goes out through the
router. The Windows side is an adapter (`adapters/media_sessions.py`); this module is
protocol-agnostic and tested with fakes.

- **Event-driven.** The adapter calls back when a session, its media, its playback state or
  its timeline changes; the watcher re-reads and publishes `PcNowPlayingChanged`. No polling.
- **Throttled.** Some apps report the timeline several times a second. Timeline changes are
  read at most once per `timeline_interval` and published only when the position jumps (a
  seek), not while it moves as expected: the UI counts on from `position_at` itself.
- **No flicker.** Browsers drop their session for a moment when a track changes, so a session
  that disappears is reported gone only if it stays gone for `vanish_grace` seconds.
- **Commands are confirmed.** An app can "accept" a command and do nothing (Music spike 1), so
  after each one the watcher re-reads until the state shows it worked.
- **Private.** Titles, artists, albums and artwork are personal: shown in the window, never
  logged, never in diagnostics. Artwork stays in memory; it is never written to disk.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
import time
from collections.abc import Callable, Coroutine
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from tandem.engine.events import Event, EventBus

_LOGGER = logging.getLogger(__name__)

_FIREFOX_ID = re.compile(r"[0-9A-Fa-f]{16}")


class PcMediaCommand(Enum):
    PLAY_PAUSE = "play_pause"
    NEXT = "next"
    PREVIOUS = "previous"


class ChangeKind(Enum):
    """What the adapter says has changed."""

    SESSION = "session"  # a session came or went, or another one became current
    MEDIA = "media"  # title, artist, album or artwork
    PLAYBACK = "playback"  # playing / paused, or which controls the app allows
    TIMELINE = "timeline"  # position or length


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
    can_seek: bool = False
    position: float | None = None
    """Seconds into the item at `position_at`; None for live streams."""
    duration: float | None = None
    """Length in seconds; None when the app doesn't say (live radio)."""
    position_at: float = 0.0
    """Monotonic clock time of `position` (set by the watcher)."""
    has_artwork: bool = False
    artwork_id: int | None = None
    """Changes whenever the artwork does; None when there is none (set by the watcher)."""

    def position_now(self, now: float) -> float | None:
        """Where playback is at monotonic time `now`."""
        if self.position is None:
            return None
        position = self.position
        if self.state == "playing":
            position += max(0.0, now - self.position_at)
        return position if self.duration is None else min(position, self.duration)


@dataclass(frozen=True, slots=True)
class PcArtwork:
    data: bytes
    mimetype: str


@dataclass(frozen=True, slots=True)
class PcNowPlayingChanged(Event):
    now_playing: PcNowPlaying | None = None


class MediaSessions(Protocol):
    async def watch(self, on_change: Callable[[ChangeKind], None]) -> None:
        """Start watching. `on_change` must be called on the asyncio loop thread."""
        ...

    async def unwatch(self) -> None: ...

    async def current(self) -> PcNowPlaying | None:
        """The session Windows considers current, or None when nothing reports. `position`
        is as of the moment of reading."""
        ...

    async def artwork(self) -> PcArtwork | None: ...

    async def command(self, command: PcMediaCommand) -> bool:
        """Send a command to the current session. False if there is none or it refused.
        True means only that the app took it, not that it worked."""
        ...

    async def seek(self, position: float) -> bool: ...


Sleep = Callable[[float], Coroutine[Any, Any, None]]


def _media_key(reading: PcNowPlaying) -> tuple[object, ...]:
    return (reading.app, reading.title, reading.artist, reading.album, reading.has_artwork)


class PcMediaWatcher:
    def __init__(
        self,
        bus: EventBus,
        sessions: MediaSessions,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        timeline_interval: float = 1.0,
        drift_tolerance: float = 1.5,
        confirm_timeout: float = 3.0,
        vanish_grace: float = 1.0,
    ) -> None:
        self._bus = bus
        self._sessions = sessions
        self._clock = clock
        self._sleep = sleep
        self._timeline_interval = timeline_interval
        self._drift_tolerance = drift_tolerance
        self._confirm_timeout = confirm_timeout
        self._vanish_grace = vanish_grace
        self._vanishing: asyncio.Task[None] | None = None
        self.now_playing: PcNowPlaying | None = None
        self._artwork: PcArtwork | None = None
        self._artwork_id = 0
        self._media_key: tuple[object, ...] | None = None
        self._watching = False
        self._started: asyncio.Task[None] | None = None
        self._worker: asyncio.Task[None] | None = None
        self._refresh_wanted = False
        self._timeline_pending = False
        self._tasks: set[asyncio.Task[None]] = set()
        self._waiters: list[asyncio.Future[None]] = []

    @property
    def available(self) -> bool:
        """True once Windows' media controls are being watched."""
        return self._watching

    def artwork(self) -> PcArtwork | None:
        """The current session's artwork, kept in memory only."""
        playing = self.now_playing
        return self._artwork if playing is not None and playing.artwork_id is not None else None

    # Lifecycle

    def start(self) -> None:
        if self._started is None:
            self._started = asyncio.get_running_loop().create_task(self._start(), name="pc-media")

    async def wait_started(self) -> None:
        """Wait until watching has begun (or failed); for tests and start-up."""
        if self._started is not None:
            await asyncio.shield(self._started)

    async def stop(self) -> None:
        started, self._started = self._started, None
        was_watching, self._watching = self._watching, False
        tasks = [t for t in (started, self._worker, *self._tasks) if t is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._worker = None
        self._wake_waiters()
        if was_watching:
            with suppress(Exception):
                await self._sessions.unwatch()

    async def _start(self) -> None:
        try:
            await self._sessions.watch(self._on_change)
        except Exception as exc:  # no media controls on this PC, or the service is missing
            # Type name only: messages can carry system details.
            _LOGGER.warning("Now playing isn't available on this PC (%s)", type(exc).__name__)
            return
        self._watching = True
        await self.refresh()

    # Commands

    async def command(self, command: PcMediaCommand) -> bool:
        """Send `command` and wait until the app's state shows it worked."""
        before = await self._read()
        if before is None:
            return False
        try:
            accepted = await self._sessions.command(command)
        except Exception as exc:
            _LOGGER.info("A PC media command failed (%s)", type(exc).__name__)
            return False
        if not accepted:
            return False
        return await self._confirm(lambda after: _worked(command, before, after))

    async def seek(self, position: float) -> bool:
        current = self.now_playing
        if current is None or not current.can_seek or position < 0:
            return False
        if current.duration is not None:
            position = min(position, current.duration)
        try:
            accepted = await self._sessions.seek(position)
        except Exception as exc:
            _LOGGER.info("A PC media seek failed (%s)", type(exc).__name__)
            return False
        target = position
        return accepted and await self._confirm(
            lambda after: after.position is not None and abs(after.position - target) <= 2.0
        )

    async def _confirm(self, worked: Callable[[PcNowPlaying], bool]) -> bool:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._confirm_timeout
        try:
            while True:
                reading = await self._read()
                if reading is not None and worked(reading):
                    return True
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return False
                waiter: asyncio.Future[None] = loop.create_future()
                self._waiters.append(waiter)
                try:
                    await asyncio.wait_for(waiter, remaining)
                except TimeoutError:
                    pass
                finally:
                    with suppress(ValueError):
                        self._waiters.remove(waiter)
        finally:
            self._request_refresh()

    # Change handling

    def _on_change(self, kind: ChangeKind) -> None:
        if not self._watching:
            return
        self._wake_waiters()
        if kind is ChangeKind.TIMELINE:
            if not self._timeline_pending:
                self._timeline_pending = True
                self._spawn(self._timeline_refresh())
            return
        self._request_refresh()

    def _wake_waiters(self) -> None:
        waiters, self._waiters = self._waiters, []
        for waiter in waiters:
            if not waiter.done():
                waiter.set_result(None)

    async def _timeline_refresh(self) -> None:
        try:
            await self._sleep(self._timeline_interval)
        finally:
            self._timeline_pending = False
        self._request_refresh()

    def _request_refresh(self) -> None:
        """Coalesce a burst of changes into reads, one at a time."""
        if not self._watching:
            return
        self._refresh_wanted = True
        if self._worker is None or self._worker.done():
            self._worker = asyncio.get_running_loop().create_task(self._refresh_loop())

    async def _refresh_loop(self) -> None:
        while self._refresh_wanted and self._watching:
            self._refresh_wanted = False
            await self.refresh()

    async def _read(self) -> PcNowPlaying | None:
        try:
            return await self._sessions.current()
        except Exception as exc:  # Windows' media service can be busy or missing
            _LOGGER.debug("Reading the PC's media session failed (%s)", type(exc).__name__)
            return None

    async def refresh(self) -> None:
        """Read the current session and publish it if it changed."""
        reading = await self._read()
        if reading is None:
            if self.now_playing is not None and self._vanish_grace > 0:
                # Maybe a browser changing track: wait before saying nothing plays.
                if self._vanishing is None or self._vanishing.done():
                    self._vanishing = self._spawn(self._vanish())
                return
            self._clear()
            return
        if self._vanishing is not None:
            self._vanishing.cancel()
            self._vanishing = None
        await self._apply(reading)

    async def _vanish(self) -> None:
        await self._sleep(self._vanish_grace)
        self._vanishing = None
        reading = await self._read()
        if reading is None:
            self._clear()
        else:
            await self._apply(reading)

    def _clear(self) -> None:
        self._media_key = None
        self._artwork = None
        self._publish(None)

    async def _apply(self, reading: PcNowPlaying) -> None:
        key = _media_key(reading)
        if key != self._media_key:
            self._media_key = key
            self._artwork = await self._fetch_artwork() if reading.has_artwork else None
            if self._artwork is not None:
                self._artwork_id += 1
        self._publish(
            dataclasses.replace(
                reading,
                position_at=self._clock(),
                artwork_id=self._artwork_id if self._artwork is not None else None,
            )
        )

    async def _fetch_artwork(self) -> PcArtwork | None:
        try:
            return await self._sessions.artwork()
        except Exception as exc:
            _LOGGER.debug("Reading the artwork failed (%s)", type(exc).__name__)
            return None

    def _publish(self, now_playing: PcNowPlaying | None) -> None:
        if not self._differs(self.now_playing, now_playing):
            return
        self.now_playing = now_playing
        self._bus.publish(PcNowPlayingChanged(now_playing))

    def _differs(self, old: PcNowPlaying | None, new: PcNowPlaying | None) -> bool:
        """True unless only the position moved, and by about as much as time did."""
        if old is None or new is None:
            return old != new
        if dataclasses.replace(old, position=None, position_at=0.0) != dataclasses.replace(
            new, position=None, position_at=0.0
        ):
            return True
        expected = old.position_now(new.position_at)
        if expected is None or new.position is None:
            return (expected is None) != (new.position is None)
        return abs(new.position - expected) > self._drift_tolerance

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task


def _worked(command: PcMediaCommand, before: PcNowPlaying, after: PcNowPlaying) -> bool:
    """Whether `after` shows that `command` took effect."""
    if command is PcMediaCommand.PLAY_PAUSE:
        return (after.state == "playing") != (before.state == "playing")
    # NEXT and PREVIOUS: another item, or the same one from the start ("previous" restarts).
    if (after.app, after.title, after.artist, after.album) != (
        before.app,
        before.title,
        before.artist,
        before.album,
    ):
        return True
    return (
        after.position is not None
        and before.position is not None
        and after.position + 1.0 < before.position
    )


class NoMediaSessions:
    """For PCs (and tests) without Windows' media controls."""

    async def watch(self, on_change: Callable[[ChangeKind], None]) -> None:
        return None

    async def unwatch(self) -> None:
        return None

    async def current(self) -> PcNowPlaying | None:
        return None

    async def artwork(self) -> PcArtwork | None:
        return None

    async def command(self, command: PcMediaCommand) -> bool:
        return False

    async def seek(self, position: float) -> bool:
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
        ("brave", "Brave"),
        ("opera", "Opera"),
        ("zunemusic", "Media Player"),
        ("vlc", "VLC"),
    )
    for needle, name in known:
        if needle in lowered:
            return name
    base = app_id.split("!")[0].rsplit("\\", 1)[-1]
    if _FIREFOX_ID.fullmatch(base):  # Firefox: a hash of its install folder
        return "Firefox"
    if base.lower().endswith(".exe"):
        base = base[:-4]
    if "_" in base:  # Package.Name_publisherhash, or Name_publisherhash
        base = base.split("_")[0].split(".")[-1]
    return base or None
