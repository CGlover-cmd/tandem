"""Windows' media controls (GSMTC) through the pywinrt projections (Music spike 1).

The only module that imports `winrt`, and only once `watch` runs on the asyncio loop thread.
WinRT raises its change events on its own thread pool; each one is handed to the loop with
`call_soon_threadsafe`. Nothing read here is logged: titles, artists and artwork go to the
engine's `PcMediaWatcher`, and from there to the window only.
"""

from __future__ import annotations

import asyncio
import importlib.util
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from tandem.engine.pc_media import (
    ChangeKind,
    MediaSessions,
    NoMediaSessions,
    PcArtwork,
    PcMediaCommand,
    PcNowPlaying,
)
from tandem.engine.pc_media import friendly_app as _friendly

# GlobalSystemMediaTransportControlsSessionPlaybackStatus, by value.
_STATUS = {4: "playing", 5: "paused", 3: "stopped"}
_PLAYING = 4

_TICKS_PER_SECOND = 10_000_000  # WinRT TimeSpan and position units: 100 ns
_MAX_ARTWORK = 4 * 1024 * 1024
_IMAGE_TYPES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF8", "image/gif"),
    (b"BM", "image/bmp"),
)

ManagerFactory = Callable[[], Awaitable[Any]]
StreamReader = Callable[[Any], Awaitable[bytes]]
Remover = Callable[[Any], None]


async def _request_manager() -> Any:  # pragma: no cover - needs Windows' media controls
    from winrt.windows.media.control import (  # pyright: ignore[reportMissingModuleSource]
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )

    return await Manager.request_async()


async def _read_thumbnail(reference: Any) -> bytes:  # pragma: no cover - needs WinRT
    from winrt.windows.storage.streams import (  # pyright: ignore[reportMissingModuleSource]
        DataReader,
        InputStreamOptions,
    )

    stream: Any = await reference.open_read_async()
    try:
        size = min(int(stream.size), _MAX_ARTWORK)
        reader: Any = DataReader(stream)
        reader.input_stream_options = InputStreamOptions.READ_AHEAD
        loaded = int(await reader.load_async(size))
        data = bytearray(loaded)
        reader.read_bytes(data)
        return bytes(data)
    finally:
        stream.close()


def image_type(data: bytes) -> str | None:
    """The image's type from its first bytes; None for anything we won't show."""
    for magic, mimetype in _IMAGE_TYPES:
        if data.startswith(magic):
            return mimetype
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _seconds(value: Any) -> float:
    """A WinRT TimeSpan (a `timedelta` in pywinrt) in seconds."""
    try:
        return float(value.total_seconds())
    except AttributeError:
        return float(value or 0) / _TICKS_PER_SECOND


class WindowsMediaSessions:
    def __init__(
        self,
        *,
        manager_factory: ManagerFactory = _request_manager,
        read_stream: StreamReader = _read_thumbnail,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._manager_factory = manager_factory
        self._read_stream = read_stream
        self._wall_clock = wall_clock
        self._manager: Any = None
        self._manager_tokens: list[tuple[Remover, Any]] = []
        self._session: Any = None
        self._session_id: str | None = None
        self._session_tokens: list[tuple[Remover, Any]] = []
        self._notify: Callable[[ChangeKind], None] = lambda _kind: None

    # Watching

    async def watch(self, on_change: Callable[[ChangeKind], None]) -> None:
        loop = asyncio.get_running_loop()

        def dispatch(kind: ChangeKind) -> None:  # loop thread
            if kind is ChangeKind.SESSION:
                self._follow(self._pick())
            on_change(kind)

        def notify(kind: ChangeKind) -> None:  # any thread
            with suppress(RuntimeError):  # the loop has closed
                loop.call_soon_threadsafe(dispatch, kind)

        manager: Any = await self._manager_factory()
        self._manager = manager
        self._notify = notify

        def on_session(_sender: Any, _args: Any) -> None:
            notify(ChangeKind.SESSION)

        self._manager_tokens = [
            (
                manager.remove_current_session_changed,
                manager.add_current_session_changed(on_session),
            ),
            (manager.remove_sessions_changed, manager.add_sessions_changed(on_session)),
        ]
        self._follow(self._pick())

    async def unwatch(self) -> None:
        self._unhook_session()
        for remove, token in self._manager_tokens:
            with suppress(Exception):
                remove(token)
        self._manager_tokens = []
        self._manager = None
        self._notify = lambda _kind: None

    def _pick(self) -> Any:
        """Windows' current session; else one that is playing; else any."""
        manager: Any = self._manager
        if manager is None:
            return None
        current: Any = manager.get_current_session()
        if current is not None:
            return current
        sessions: list[Any] = list(manager.get_sessions())
        for session in sessions:
            if int(session.get_playback_info().playback_status) == _PLAYING:
                return session
        return sessions[0] if sessions else None

    def _follow(self, session: Any) -> None:
        # Always hook afresh: a browser re-makes its session (same app id, new object) on
        # every track change, and the old object's events never fire again.
        self._unhook_session()
        if session is None:
            return
        self._session = session
        self._session_id = str(session.source_app_user_model_id)
        notify = self._notify

        def handler(kind: ChangeKind) -> Callable[[Any, Any], None]:
            return lambda _sender, _args: notify(kind)

        self._session_tokens = [
            (
                session.remove_media_properties_changed,
                session.add_media_properties_changed(handler(ChangeKind.MEDIA)),
            ),
            (
                session.remove_playback_info_changed,
                session.add_playback_info_changed(handler(ChangeKind.PLAYBACK)),
            ),
            (
                session.remove_timeline_properties_changed,
                session.add_timeline_properties_changed(handler(ChangeKind.TIMELINE)),
            ),
        ]

    def _unhook_session(self) -> None:
        for remove, token in self._session_tokens:
            with suppress(Exception):
                remove(token)
        self._session_tokens = []
        self._session, self._session_id = None, None

    # Reading

    async def current(self) -> PcNowPlaying | None:
        session: Any = self._session
        if session is None:
            return None
        info: Any = session.get_playback_info()
        status = int(info.playback_status)
        controls: Any = info.controls
        position, duration = self._timeline(session, status == _PLAYING)
        props: Any = await session.try_get_media_properties_async()
        return PcNowPlaying(
            state=_STATUS.get(status, "other"),
            title=props.title or None,
            artist=props.artist or props.album_artist or None,
            album=props.album_title or None,
            app=_friendly(session.source_app_user_model_id),
            can_play_pause=bool(
                controls.is_play_pause_toggle_enabled
                or controls.is_play_enabled
                or controls.is_pause_enabled
            ),
            can_next=bool(controls.is_next_enabled),
            can_previous=bool(controls.is_previous_enabled),
            can_seek=bool(controls.is_playback_position_enabled) and duration is not None,
            position=position,
            duration=duration,
            has_artwork=props.thumbnail is not None,
        )

    def _timeline(self, session: Any, playing: bool) -> tuple[float | None, float | None]:
        timeline: Any = session.get_timeline_properties()
        start = _seconds(timeline.start_time)
        end = _seconds(timeline.end_time)
        if end <= start:
            return None, None  # a live stream, or an app that doesn't report a timeline
        duration = end - start
        position = max(0.0, _seconds(timeline.position) - start)
        if playing:
            # Apps report the position as of `last_updated_time`; some only on a seek or a new
            # track, so count on from then.
            updated: Any = timeline.last_updated_time
            with suppress(AttributeError, OSError, OverflowError, ValueError, TypeError):
                if updated is not None and updated.year > 1601:
                    age = self._wall_clock() - float(updated.timestamp())
                    if 0 <= age <= duration:
                        position += age
        return min(position, duration), duration

    async def artwork(self) -> PcArtwork | None:
        session: Any = self._session
        if session is None:
            return None
        props: Any = await session.try_get_media_properties_async()
        if props.thumbnail is None:
            return None
        data = await self._read_stream(props.thumbnail)
        mimetype = image_type(data)
        return None if mimetype is None else PcArtwork(data, mimetype)

    # Commands

    async def command(self, command: PcMediaCommand) -> bool:
        session: Any = self._session
        if session is None:
            return False
        if command is PcMediaCommand.NEXT:
            return bool(await session.try_skip_next_async())
        if command is PcMediaCommand.PREVIOUS:
            return bool(await session.try_skip_previous_async())
        info: Any = session.get_playback_info()
        if info.controls.is_play_pause_toggle_enabled:
            return bool(await session.try_toggle_play_pause_async())
        # Some apps offer only play or only pause; pick what fits.
        if int(info.playback_status) == _PLAYING:
            return bool(await session.try_pause_async())
        return bool(await session.try_play_async())

    async def seek(self, position: float) -> bool:
        session: Any = self._session
        if session is None:
            return False
        timeline: Any = session.get_timeline_properties()
        target = _seconds(timeline.start_time) + position
        return bool(
            await session.try_change_playback_position_async(int(target * _TICKS_PER_SECOND))
        )


def media_sessions() -> MediaSessions:  # pragma: no cover - depends on the PC
    try:
        found = importlib.util.find_spec("winrt.windows.media.control") is not None
    except (ImportError, ValueError):
        found = False
    return WindowsMediaSessions() if found else NoMediaSessions()
