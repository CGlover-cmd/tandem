"""What the PC is playing, from the engine to the window's contract (tandem.bridge, Phase 6)."""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from conftest import FakeBackend, ManualSleep
from tandem import bridge
from tandem.engine.events import EventBus
from tandem.engine.pc_media import ChangeKind, PcArtwork, PcMediaCommand, PcNowPlaying
from tandem.engine.service import Engine
from tandem.engine.settings import SettingsStore
from tandem.ui import backend as ui

SONG = PcNowPlaying(
    "playing",
    "Example Song",
    "Example Artist",
    "Example Album",
    "Apple Music",
    can_play_pause=True,
    can_next=True,
    can_seek=True,
    position=20.0,
    duration=180.0,
    has_artwork=True,
)


class Harness:
    def __init__(self, tmp_path: Path, sleep: ManualSleep) -> None:
        self.fake = FakeBackend([])
        self.fake.sessions.now = SONG
        self.fake.sessions.art = PcArtwork(b"\xff\xd8\xff-invented", "image/jpeg")
        bus = EventBus()
        self.engine = Engine(self.fake, bus=bus, sleep=sleep, discovery_interval=60.0)
        self.engine.pc_media._confirm_timeout = 0.05  # pyright: ignore[reportPrivateUsage]
        self.engine.pc_media._vanish_grace = 0  # pyright: ignore[reportPrivateUsage]
        settings = SettingsStore(tmp_path / "settings.json", bus)
        self.backend = bridge.EngineBackend(self.engine, settings)
        self.events: list[ui.BackendEvent] = []
        self.backend.subscribe(self.events.append)

    def music_events(self) -> list[ui.MusicSnapshot | None]:
        return [e.music for e in self.events if isinstance(e, ui.MusicChanged)]


@pytest.fixture
async def h(tmp_path: Path, manual_sleep: ManualSleep) -> AsyncIterator[Harness]:
    harness = Harness(tmp_path, manual_sleep)
    await harness.backend.start()
    await harness.engine.pc_media.wait_started()
    yield harness
    await harness.backend.stop()


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


async def test_start_watches_the_pcs_media(h: Harness) -> None:
    music = h.backend.music()
    assert music is not None
    assert (music.app, music.state, music.title, music.duration) == (
        "Apple Music",
        "playing",
        "Example Song",
        180.0,
    )
    assert music.commands == frozenset({ui.MusicCommand.PLAY_PAUSE, ui.MusicCommand.NEXT})
    assert music.can_seek
    assert music.artwork == 1
    assert h.music_events() == [music]
    art = h.backend.music_artwork()
    assert art == ui.MusicArtwork(b"\xff\xd8\xff-invented", "image/jpeg")


async def test_changes_reach_the_window(h: Harness) -> None:
    h.fake.sessions.now = dataclasses.replace(SONG, title="Second Example Song")
    h.fake.sessions.change(ChangeKind.MEDIA)
    await _settle()
    last = h.music_events()[-1]
    assert last is not None
    assert last.title == "Second Example Song"

    h.fake.sessions.now = None
    h.fake.sessions.change(ChangeKind.SESSION)
    await _settle()
    assert h.music_events()[-1] is None
    assert h.backend.music() is None
    assert h.backend.music_artwork() is None


async def test_commands(h: Harness) -> None:
    await h.backend.music_command(ui.MusicCommand.PLAY_PAUSE)
    await h.backend.music_command(ui.MusicCommand.NEXT)
    await h.backend.music_seek(60.0)
    assert h.fake.sessions.commands == [PcMediaCommand.PLAY_PAUSE, PcMediaCommand.NEXT]
    assert h.fake.sessions.seeks == [60.0]


async def test_command_problems_are_words_for_the_window(h: Harness) -> None:
    with pytest.raises(ui.ControlError, match="appCant"):
        await h.backend.music_command(ui.MusicCommand.PREVIOUS)  # the app has it off
    with pytest.raises(ui.ControlError, match="appCant"):
        await h.backend.music_seek(-5.0)

    h.fake.sessions.react = False  # the app accepts and does nothing
    with pytest.raises(ui.ControlError, match="appDidntRespond"):
        await h.backend.music_command(ui.MusicCommand.NEXT)
    with pytest.raises(ui.ControlError, match="appDidntRespond"):
        await h.backend.music_seek(30.0)

    h.fake.sessions.now = None
    h.fake.sessions.change(ChangeKind.SESSION)
    await _settle()
    with pytest.raises(ui.ControlError, match="nothingPlaying"):
        await h.backend.music_command(ui.MusicCommand.PLAY_PAUSE)
    with pytest.raises(ui.ControlError, match="nothingPlaying"):
        await h.backend.music_seek(1.0)


async def test_live_streams_cant_seek(h: Harness) -> None:
    h.fake.sessions.now = dataclasses.replace(SONG, position=None, duration=None, can_seek=False)
    h.fake.sessions.change(ChangeKind.TIMELINE)
    await _settle()
    h.engine.pc_media._timeline_pending = False  # pyright: ignore[reportPrivateUsage]
    await h.engine.pc_media.refresh()
    music = h.backend.music()
    assert music is not None
    assert not music.can_seek
    with pytest.raises(ui.ControlError, match="appCant"):
        await h.backend.music_seek(10.0)
