"""What the PC is playing (Phase 6). Titles are invented (docs/PRIVACY.md)."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import AsyncIterator

import pytest

from conftest import FakeClock, FakeSessions, ManualSleep
from tandem.engine.events import EventBus
from tandem.engine.pc_media import (
    ChangeKind,
    NoMediaSessions,
    PcArtwork,
    PcMediaCommand,
    PcMediaWatcher,
    PcNowPlaying,
    PcNowPlayingChanged,
    friendly_app,
)

SONG = PcNowPlaying(
    "playing",
    "Example Song",
    "Example Artist",
    "Example Album",
    "Spotify",
    True,
    True,
    True,
    can_seek=True,
    position=10.0,
    duration=200.0,
    has_artwork=True,
)
ART = PcArtwork(b"\xff\xd8\xff-invented-jpeg", "image/jpeg")


class Harness:
    def __init__(self, sleep: ManualSleep, clock: FakeClock) -> None:
        self.bus = EventBus()
        self.sessions = FakeSessions()
        self.sessions.now = SONG
        self.sessions.art = ART
        self.clock = clock
        self.sleep = sleep
        self.seen: list[PcNowPlaying | None] = []
        self.bus.subscribe(PcNowPlayingChanged, lambda e: self.seen.append(e.now_playing))
        self.watcher = PcMediaWatcher(
            self.bus, self.sessions, clock=clock, sleep=sleep, confirm_timeout=0.05
        )

    async def settle(self) -> None:
        for _ in range(20):
            await asyncio.sleep(0)


@pytest.fixture
async def h(manual_sleep: ManualSleep, clock: FakeClock) -> AsyncIterator[Harness]:
    harness = Harness(manual_sleep, clock)
    harness.watcher.start()
    harness.watcher.start()  # once
    await harness.watcher.wait_started()
    yield harness
    await harness.watcher.stop()


async def test_publishes_the_session_with_artwork_on_start(h: Harness) -> None:
    assert h.watcher.available
    assert len(h.seen) == 1
    playing = h.seen[0]
    assert playing is not None
    assert (playing.title, playing.app, playing.position_at) == ("Example Song", "Spotify", 1000.0)
    assert playing.artwork_id == 1
    assert h.watcher.artwork() == ART


async def test_follows_change_events_without_polling(h: Harness) -> None:
    reads = h.sessions.reads
    await h.settle()
    assert h.sessions.reads == reads  # nothing happens between events

    h.sessions.now = dataclasses.replace(SONG, title="Second Example Song", position=0.0)
    h.sessions.change(ChangeKind.MEDIA)
    await h.settle()
    assert h.seen[-1] is not None
    assert h.seen[-1].title == "Second Example Song"
    assert h.seen[-1].artwork_id == 2  # a new track: the artwork is read again
    assert h.sessions.art_reads == 2


async def test_bursts_of_changes_are_read_together(h: Harness) -> None:
    reads = h.sessions.reads
    for _ in range(5):
        h.sessions.change(ChangeKind.PLAYBACK)
    await h.settle()
    assert h.sessions.reads - reads <= 2


async def test_same_track_keeps_its_artwork(h: Harness) -> None:
    h.sessions.now = dataclasses.replace(SONG, state="paused")
    h.sessions.change(ChangeKind.PLAYBACK)
    await h.settle()
    assert h.seen[-1] is not None
    assert h.seen[-1].state == "paused"
    assert h.seen[-1].artwork_id == 1
    assert h.sessions.art_reads == 1


async def test_timeline_changes_are_throttled_and_steady_progress_is_not_published(
    h: Harness,
) -> None:
    published = len(h.seen)
    reads = h.sessions.reads
    for _ in range(10):  # an app reporting the timeline several times a second
        h.sessions.change(ChangeKind.TIMELINE)
    await h.settle()
    assert h.sleep.delays == [1.0]  # one throttled read waiting
    assert h.sessions.reads == reads

    # Five seconds on, the app reports five seconds further: as expected, so nothing new.
    h.clock.now += 5
    h.sessions.now = dataclasses.replace(SONG, position=15.0)
    h.sleep.release()
    await h.settle()
    assert h.sessions.reads == reads + 1
    assert len(h.seen) == published

    # A seek elsewhere (the user dragged in the app) is a jump: published.
    h.sessions.now = dataclasses.replace(SONG, position=120.0)
    h.sessions.change(ChangeKind.TIMELINE)
    await h.settle()
    h.sleep.release()
    await h.settle()
    assert h.seen[-1] is not None
    assert h.seen[-1].position == 120.0


async def test_paused_position_counts_as_steady(h: Harness) -> None:
    paused = dataclasses.replace(SONG, state="paused")
    h.sessions.now = paused
    h.sessions.change(ChangeKind.PLAYBACK)
    await h.settle()
    published = len(h.seen)
    h.clock.now += 30
    h.sessions.change(ChangeKind.TIMELINE)
    await h.settle()
    h.sleep.release()
    await h.settle()
    assert len(h.seen) == published


async def test_live_streams_have_no_position(h: Harness) -> None:
    h.sessions.now = dataclasses.replace(SONG, position=None, duration=None, can_seek=False)
    h.sessions.change(ChangeKind.TIMELINE)
    await h.settle()
    h.sleep.release()
    await h.settle()
    playing = h.seen[-1]
    assert playing is not None
    assert playing.position is None
    assert playing.position_now(h.clock.now + 10) is None


async def test_session_going_away_publishes_none_after_a_grace(h: Harness) -> None:
    h.sessions.now = None
    h.sessions.change(ChangeKind.SESSION)
    await h.settle()
    assert h.seen[-1] is not None  # still shown during the grace
    assert h.sleep.delays == [1.0]
    h.sleep.release()
    await h.settle()
    assert h.seen[-1] is None
    assert h.watcher.artwork() is None


async def test_a_browser_changing_track_doesnt_flicker(h: Harness) -> None:
    published = len(h.seen)
    h.sessions.now = None  # the browser drops its session for a moment...
    h.sessions.change(ChangeKind.SESSION)
    await h.settle()
    h.sessions.now = dataclasses.replace(SONG, title="Second Example Song", position=0.0)
    h.sessions.change(ChangeKind.SESSION)  # ...and brings one back with the next track
    await h.settle()
    h.sleep.release()
    await h.settle()
    titles = [p.title if p else None for p in h.seen[published:]]
    assert titles == ["Second Example Song"]


async def test_a_session_back_by_the_end_of_the_grace_is_kept(h: Harness) -> None:
    h.sessions.now = None
    h.sessions.change(ChangeKind.SESSION)
    await h.settle()
    h.sessions.now = SONG  # back, without an event in between
    h.sleep.release()
    await h.settle()
    assert all(playing is not None for playing in h.seen)


async def test_commands_are_confirmed_by_the_new_state(h: Harness) -> None:
    assert await h.watcher.command(PcMediaCommand.PLAY_PAUSE)
    await h.settle()
    assert h.seen[-1] is not None
    assert h.seen[-1].state == "paused"
    assert await h.watcher.command(PcMediaCommand.NEXT)
    assert await h.watcher.command(PcMediaCommand.PREVIOUS)
    assert h.sessions.commands == [
        PcMediaCommand.PLAY_PAUSE,
        PcMediaCommand.NEXT,
        PcMediaCommand.PREVIOUS,
    ]


async def test_previous_restarting_the_same_track_counts(h: Harness) -> None:
    h.sessions.react = False
    h.sessions.now = dataclasses.replace(SONG, position=80.0)

    async def restart() -> None:
        await asyncio.sleep(0.01)
        h.sessions.now = dataclasses.replace(SONG, position=0.5)
        h.sessions.change(ChangeKind.TIMELINE)

    task = asyncio.create_task(restart())
    assert await h.watcher.command(PcMediaCommand.PREVIOUS)
    await task


async def test_an_accepted_command_that_changes_nothing_is_not_confirmed(h: Harness) -> None:
    h.sessions.react = False  # the app says yes and does nothing
    assert not await h.watcher.command(PcMediaCommand.NEXT)
    assert not await h.watcher.command(PcMediaCommand.PLAY_PAUSE)


async def test_seek(h: Harness) -> None:
    assert await h.watcher.seek(500.0)  # past the end: clamped to the length
    assert h.sessions.seeks == [200.0]
    assert not await h.watcher.seek(-1.0)
    h.sessions.react = False
    assert not await h.watcher.seek(50.0)


async def test_cannot_seek_a_live_stream(h: Harness) -> None:
    h.sessions.now = dataclasses.replace(SONG, can_seek=False)
    h.sessions.change(ChangeKind.PLAYBACK)
    await h.settle()
    assert not await h.watcher.seek(30.0)
    assert h.sessions.seeks == []


async def test_failures_are_quiet_and_never_log_titles(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    h.sessions.fail = OSError("Example Song by Example Artist")
    assert not await h.watcher.command(PcMediaCommand.NEXT)
    await h.watcher.refresh()
    await h.settle()
    h.sleep.release()  # the grace before "nothing playing"
    await h.settle()
    assert h.seen[-1] is None
    h.sessions.fail = None
    h.sessions.now = SONG

    async def broken(_command: PcMediaCommand) -> bool:
        raise OSError("Example Song")

    h.sessions.command = broken  # type: ignore[method-assign]
    assert not await h.watcher.command(PcMediaCommand.NEXT)

    async def broken_seek(_position: float) -> bool:
        raise OSError("Example Song")

    h.sessions.seek = broken_seek  # type: ignore[method-assign]
    assert not await h.watcher.seek(1.0)
    assert "Example" not in caplog.text


async def test_artwork_that_cant_be_read_is_skipped(h: Harness) -> None:
    async def broken() -> PcArtwork | None:
        raise OSError("busy")

    h.sessions.artwork = broken  # type: ignore[method-assign]
    h.sessions.now = dataclasses.replace(SONG, title="Second Example Song")
    h.sessions.change(ChangeKind.MEDIA)
    await h.settle()
    assert h.seen[-1] is not None
    assert h.seen[-1].artwork_id is None
    assert h.watcher.artwork() is None


async def test_stop_unwatches_and_ignores_late_events(h: Harness) -> None:
    await h.watcher.stop()
    assert h.sessions.unwatched
    assert not h.watcher.available
    published = len(h.seen)
    h.sessions.change(ChangeKind.MEDIA)
    await h.settle()
    assert len(h.seen) == published


async def test_no_media_controls_on_this_pc(
    manual_sleep: ManualSleep, clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness(manual_sleep, clock)
    harness.sessions.watch_fail = ImportError("winrt")
    harness.watcher.start()
    await harness.watcher.wait_started()
    assert not harness.watcher.available
    assert harness.seen == []
    assert "isn't available" in caplog.text
    await harness.watcher.stop()
    assert not harness.sessions.unwatched


async def test_no_sessions() -> None:
    sessions = NoMediaSessions()
    await sessions.watch(lambda _kind: None)
    await sessions.unwatch()
    assert await sessions.current() is None
    assert await sessions.artwork() is None
    assert not await sessions.command(PcMediaCommand.NEXT)
    assert not await sessions.seek(1.0)


def test_position_now() -> None:
    playing = dataclasses.replace(SONG, position=10.0, position_at=100.0)
    assert playing.position_now(105.0) == 15.0
    assert playing.position_now(1000.0) == 200.0  # never past the end
    assert dataclasses.replace(playing, state="paused").position_now(105.0) == 10.0


def test_friendly_app_names() -> None:
    assert friendly_app("Spotify.exe") == "Spotify"
    assert friendly_app("AppleInc.AppleMusicWin_abcdefghijk!App") == "Apple Music"
    assert friendly_app("MSEdge") == "Microsoft Edge"
    assert friendly_app("Contoso_abcdefghijk!App") == "Contoso"
    assert friendly_app("AAAABBBBCCCCDDDD") == "Firefox"  # Firefox's id: 16 hex digits
    assert friendly_app("Contoso.ExamplePlayer_abcdefghijk!App") == "ExamplePlayer"
    assert friendly_app("C:\\Tools\\player.exe") == "player"
    assert friendly_app(None) is None
    assert friendly_app("") is None
