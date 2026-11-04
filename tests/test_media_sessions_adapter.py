"""The GSMTC adapter, against fakes shaped like the pywinrt objects. Titles are invented."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from tandem.engine.adapters.media_sessions import WindowsMediaSessions, image_type
from tandem.engine.pc_media import ChangeKind, PcMediaCommand

Handler = Callable[[Any, Any], None]
NOW = 1_800_000_000.0  # the fake wall clock


class Event:
    def __init__(self) -> None:
        self.handlers: dict[int, Handler] = {}
        self._next = 0

    def add(self, handler: Handler) -> int:
        self._next += 1
        self.handlers[self._next] = handler
        return self._next

    def remove(self, token: int) -> None:
        del self.handlers[token]

    def fire(self) -> None:
        for handler in list(self.handlers.values()):
            handler(None, None)


class Obj:
    def __init__(self, **fields: Any) -> None:
        self.__dict__.update(fields)


def controls(**on: bool) -> Obj:
    names = ("play", "pause", "play_pause_toggle", "next", "previous", "playback_position")
    return Obj(**{f"is_{name}_enabled": on.get(name, False) for name in names})


class FakeSession:
    def __init__(self, app_id: str, status: int = 4) -> None:
        self.source_app_user_model_id = app_id
        self.status = status
        self.controls = controls(
            pause=True, play_pause_toggle=True, next=True, playback_position=True
        )
        self.props: Any = Obj(
            title="Example Song",
            artist="",
            album_artist="Example Artist",
            album_title="Example Album",
            thumbnail=object(),
        )
        self.timeline: Any = Obj(
            start_time=timedelta(0),
            end_time=timedelta(seconds=200),
            position=timedelta(seconds=10),
            last_updated_time=datetime.fromtimestamp(NOW - 5, UTC),
        )
        self.media_event, self.playback_event, self.timeline_event = Event(), Event(), Event()
        self.calls: list[Any] = []
        self.add_media_properties_changed = self.media_event.add
        self.remove_media_properties_changed = self.media_event.remove
        self.add_playback_info_changed = self.playback_event.add
        self.remove_playback_info_changed = self.playback_event.remove
        self.add_timeline_properties_changed = self.timeline_event.add
        self.remove_timeline_properties_changed = self.timeline_event.remove

    def get_playback_info(self) -> Obj:
        return Obj(playback_status=self.status, controls=self.controls)

    def get_timeline_properties(self) -> Obj:
        return self.timeline

    async def try_get_media_properties_async(self) -> Obj:
        return self.props

    async def _call(self, name: str, *args: Any) -> bool:
        self.calls.append((name, *args))
        return True

    def try_toggle_play_pause_async(self) -> Any:
        return self._call("toggle")

    def try_play_async(self) -> Any:
        return self._call("play")

    def try_pause_async(self) -> Any:
        return self._call("pause")

    def try_skip_next_async(self) -> Any:
        return self._call("next")

    def try_skip_previous_async(self) -> Any:
        return self._call("previous")

    def try_change_playback_position_async(self, ticks: int) -> Any:
        return self._call("seek", ticks)


class FakeManager:
    def __init__(self, *sessions: FakeSession, current: FakeSession | None = None) -> None:
        self.sessions = list(sessions)
        self.current = current
        self.current_event, self.sessions_event = Event(), Event()
        self.add_current_session_changed = self.current_event.add
        self.remove_current_session_changed = self.current_event.remove
        self.add_sessions_changed = self.sessions_event.add
        self.remove_sessions_changed = self.sessions_event.remove

    def get_current_session(self) -> FakeSession | None:
        return self.current

    def get_sessions(self) -> list[FakeSession]:
        return self.sessions


def adapter(manager: FakeManager, image: bytes = b"\xff\xd8\xff-jpeg") -> WindowsMediaSessions:
    async def factory() -> FakeManager:
        return manager

    async def read(_thumbnail: Any) -> bytes:
        return image

    return WindowsMediaSessions(manager_factory=factory, read_stream=read, wall_clock=lambda: NOW)


async def settle() -> None:
    for _ in range(10):
        await asyncio.sleep(0)


async def test_reads_the_current_session() -> None:
    session = FakeSession("AppleInc.AppleMusicWin_abcdefghijk!App")
    windows = adapter(FakeManager(session, current=session))
    await windows.watch(lambda _kind: None)

    playing = await windows.current()

    assert playing is not None
    assert (playing.state, playing.title, playing.artist, playing.album, playing.app) == (
        "playing",
        "Example Song",
        "Example Artist",  # the album artist when the artist is empty
        "Example Album",
        "Apple Music",
    )
    assert (playing.can_play_pause, playing.can_next, playing.can_previous) == (True, True, False)
    assert playing.can_seek
    assert playing.has_artwork
    assert playing.duration == 200.0
    assert playing.position == 15.0  # reported 5 s ago while playing: counted on


async def test_live_streams_and_paused_sessions() -> None:
    session = FakeSession("Spotify.exe", status=5)
    windows = adapter(FakeManager(session, current=session))
    await windows.watch(lambda _kind: None)
    playing = await windows.current()
    assert playing is not None
    assert playing.state == "paused"
    assert playing.position == 10.0

    session.timeline.end_time = timedelta(0)  # no timeline: a live stream
    playing = await windows.current()
    assert playing is not None
    assert (playing.position, playing.duration, playing.can_seek) == (None, None, False)


async def test_picks_a_playing_session_when_windows_names_none() -> None:
    paused = FakeSession("Contoso.Paused_abc!App", status=5)
    playing = FakeSession("MSEdge", status=4)
    windows = adapter(FakeManager(paused, playing))
    await windows.watch(lambda _kind: None)
    found = await windows.current()
    assert found is not None
    assert found.app == "Microsoft Edge"

    windows = adapter(FakeManager(paused))
    await windows.watch(lambda _kind: None)
    found = await windows.current()
    assert found is not None
    assert found.state == "paused"

    windows = adapter(FakeManager())
    await windows.watch(lambda _kind: None)
    assert await windows.current() is None
    assert await windows.artwork() is None
    assert not await windows.command(PcMediaCommand.NEXT)
    assert not await windows.seek(1.0)


async def test_events_from_winrt_threads_reach_the_loop() -> None:
    first = FakeSession("Spotify.exe")
    manager = FakeManager(first, current=first)
    windows = adapter(manager)
    seen: list[tuple[ChangeKind, str]] = []
    await windows.watch(lambda kind: seen.append((kind, threading.current_thread().name)))

    for event in (first.media_event, first.playback_event, first.timeline_event):
        thread = threading.Thread(target=event.fire, name="winrt-pool")
        thread.start()
        thread.join()
    await settle()
    loop_thread = threading.current_thread().name
    assert seen == [
        (ChangeKind.MEDIA, loop_thread),
        (ChangeKind.PLAYBACK, loop_thread),
        (ChangeKind.TIMELINE, loop_thread),
    ]

    # Another app becomes current: the adapter follows it and drops the old one's events.
    second = FakeSession("MSEdge")
    manager.sessions.append(second)
    manager.current = second
    manager.current_event.fire()
    await settle()
    assert seen[-1][0] is ChangeKind.SESSION
    assert not first.media_event.handlers
    assert second.media_event.handlers
    found = await windows.current()
    assert found is not None
    assert found.app == "Microsoft Edge"

    # The browser re-makes its session on a track change: same app id, a new object.
    remade = FakeSession("MSEdge")
    remade.props.title = "Second Example Song"
    manager.sessions = [first, remade]
    manager.current = remade
    manager.sessions_event.fire()
    await settle()
    assert not second.media_event.handlers
    assert len(remade.media_event.handlers) == 1
    remade.media_event.fire()  # its events now reach Tandem
    await settle()
    assert seen[-1][0] is ChangeKind.MEDIA
    found = await windows.current()
    assert found is not None
    assert found.title == "Second Example Song"
    second = remade

    await windows.unwatch()
    assert not second.media_event.handlers
    assert not manager.current_event.handlers
    assert not manager.sessions_event.handlers


async def test_commands() -> None:
    session = FakeSession("Spotify.exe")
    windows = adapter(FakeManager(session, current=session))
    await windows.watch(lambda _kind: None)

    assert await windows.command(PcMediaCommand.PLAY_PAUSE)
    assert await windows.command(PcMediaCommand.NEXT)
    assert await windows.command(PcMediaCommand.PREVIOUS)
    assert await windows.seek(30.0)
    session.controls = controls(pause=True)  # no toggle: pick pause while playing
    assert await windows.command(PcMediaCommand.PLAY_PAUSE)
    session.status = 5
    assert await windows.command(PcMediaCommand.PLAY_PAUSE)
    assert session.calls == [
        ("toggle",),
        ("next",),
        ("previous",),
        ("seek", 300_000_000),
        ("pause",),
        ("play",),
    ]


async def test_artwork() -> None:
    session = FakeSession("Spotify.exe")
    windows = adapter(FakeManager(session, current=session))
    await windows.watch(lambda _kind: None)
    art = await windows.artwork()
    assert art is not None
    assert art.mimetype == "image/jpeg"

    windows = adapter(FakeManager(session, current=session), image=b"<svg>not an image</svg>")
    await windows.watch(lambda _kind: None)
    assert await windows.artwork() is None  # only images we know are shown

    session.props.thumbnail = None
    assert await windows.artwork() is None


def test_image_types() -> None:
    assert image_type(b"\x89PNG\r\n\x1a\n....") == "image/png"
    assert image_type(b"GIF89a") == "image/gif"
    assert image_type(b"BM....") == "image/bmp"
    assert image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert image_type(b"") is None
