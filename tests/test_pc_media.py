"""What the PC is playing (Phase 6). Titles are invented (docs/PRIVACY.md)."""

from __future__ import annotations

import asyncio

from conftest import FakeSessions
from tandem.engine.events import EventBus
from tandem.engine.pc_media import (
    NoMediaSessions,
    PcMediaCommand,
    PcMediaWatcher,
    PcNowPlaying,
    PcNowPlayingChanged,
    friendly_app,
)

SONG = PcNowPlaying("playing", "Example Song", "Example Artist", None, "Spotify", True, True, True)


async def test_watcher_publishes_changes_only() -> None:
    bus = EventBus()
    seen: list[PcNowPlaying | None] = []
    bus.subscribe(PcNowPlayingChanged, lambda e: seen.append(e.now_playing))
    sessions = FakeSessions()
    watcher = PcMediaWatcher(bus, sessions, interval=0.001)
    await watcher.refresh()  # None, as before: no event
    sessions.now = SONG
    await watcher.refresh()
    await watcher.refresh()
    assert seen == [SONG]
    assert await watcher.command(PcMediaCommand.NEXT)
    assert sessions.commands == [PcMediaCommand.NEXT]

    sessions.fail = OSError("media service busy")
    await watcher.refresh()
    assert seen[-1] is None
    assert not await watcher.command(PcMediaCommand.PLAY_PAUSE)


async def test_watcher_polls_until_stopped() -> None:
    bus = EventBus()
    sessions = FakeSessions()
    sessions.now = SONG
    watcher = PcMediaWatcher(bus, sessions, interval=0.001)
    watcher.start()
    watcher.start()  # once
    for _ in range(50):
        if watcher.now_playing == SONG:
            break
        await asyncio.sleep(0.002)
    assert watcher.now_playing == SONG
    await watcher.stop()
    await watcher.stop()


async def test_no_sessions() -> None:
    sessions = NoMediaSessions()
    assert await sessions.current() is None
    assert not await sessions.command(PcMediaCommand.NEXT)


def test_friendly_app_names() -> None:
    assert friendly_app("Spotify.exe") == "Spotify"
    assert friendly_app("AppleInc.AppleMusicWin_abcdefghijk!App") == "Apple Music"
    assert friendly_app("MSEdge") == "Microsoft Edge"
    assert friendly_app("Contoso.ExamplePlayer_abcdefghijk!App") == "ExamplePlayer"
    assert friendly_app("C:\\Tools\\player.exe") == "player"
    assert friendly_app(None) is None
    assert friendly_app("") is None
