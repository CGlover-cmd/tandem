"""The music library, radio and player on the real engine (tandem.bridge_library). Folders,
tags and stations are invented (docs/PRIVACY.md)."""

from __future__ import annotations

import asyncio
import struct
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from conftest import FakeBackend, ManualSleep
from tandem import bridge
from tandem.engine.events import EventBus
from tandem.engine.library import FileEntry, LibraryArt, MusicLibrary, Tags
from tandem.engine.player import CHUNK_FRAMES
from tandem.engine.radio import Radio
from tandem.engine.service import AudioSource, Engine
from tandem.engine.settings import SettingsStore
from tandem.ui import backend as ui

TONE = struct.pack("<hh", 300, 300) * (CHUNK_FRAMES * 200)  # 2 s: long enough to stay playing


async def _until(predicate: Any, seconds: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition not reached")


class Harness:
    def __init__(self, tmp_path: Path, sleep: ManualSleep) -> None:
        self.music = tmp_path / "Music"
        album = self.music / "Daybreak"
        album.mkdir(parents=True)
        self.paths = [str(album / f"0{n} Song.mp3") for n in (1, 2, 3)]
        self.fake = FakeBackend([])
        self.fake.tracks = {path: TONE for path in self.paths}
        self.fake.tracks["http://stream.radio.example/1"] = TONE
        bus = EventBus()
        self.engine = Engine(self.fake, bus=bus, sleep=sleep, discovery_interval=60.0)

        def list_files(folder: str) -> tuple[list[FileEntry], set[str]]:
            return [FileEntry(p, 1, 1.0) for p in self.paths], set()

        def read_tags(path: str) -> Tags:
            n = self.paths.index(path) + 1
            return Tags(f"Song {n}", "Example Band", "Daybreak", None, n, 1, 2020, 2.0, n == 1)

        self.library = MusicLibrary(
            bus,
            store=None,
            list_files=list_files,
            read_tags=read_tags,
            read_art=lambda path: LibraryArt(b"\x89PNG-art", "image/png"),
        )

        async def search(query: str, limit: int) -> list[dict[str, Any]]:
            return [
                {
                    "stationuuid": "uuid-1",
                    "name": "Example FM",
                    "url_resolved": "http://stream.radio.example/1",
                    "codec": "MP3",
                    "bitrate": 128,
                }
            ]

        self.radio = Radio(bus, search, store=None)
        self.backend = bridge.EngineBackend(
            self.engine,
            SettingsStore(tmp_path / "settings.json", bus),
            library=self.library,
            radio=self.radio,
        )
        self.events: list[ui.BackendEvent] = []
        self.backend.subscribe(self.events.append)

    def player(self) -> ui.PlayerSnapshot:
        return self.backend.player()


@pytest.fixture
async def h(tmp_path: Path, manual_sleep: ManualSleep) -> AsyncIterator[Harness]:
    harness = Harness(tmp_path, manual_sleep)
    await harness.backend.start()
    await harness.backend.add_music_folder(str(harness.music))
    await harness.library.wait_idle()
    yield harness
    manual_sleep.release()
    await harness.backend.stop()


async def test_library_reaches_the_window(h: Harness) -> None:
    library = h.backend.library()
    assert library.folders == (str(h.music),)
    assert library.song_count == 3
    (album,) = library.albums
    assert (album.title, album.artist, album.year, album.track_count, album.has_art) == (
        "Daybreak",
        "Example Band",
        2020,
        3,
        True,
    )
    songs = h.backend.album_songs(album.id)
    assert [(s.title, s.number, s.album_id) for s in songs] == [
        ("Song 1", 1, album.id),
        ("Song 2", 2, album.id),
        ("Song 3", 3, album.id),
    ]
    assert [s.title for s in h.backend.search_songs("song 2")] == ["Song 2"]
    assert h.backend.library_art(album.id) == ui.MusicArtwork(b"\x89PNG-art", "image/png")
    assert h.backend.album_songs("nope") == []
    assert any(isinstance(e, ui.LibraryChanged) for e in h.events)


async def test_playing_an_album_uses_the_player_as_source(h: Harness) -> None:
    (album,) = h.backend.library().albums
    songs = h.backend.album_songs(album.id)
    await h.backend.play_album(album.id, songs[1].id)
    assert h.engine.audio_source is AudioSource.PLAYER
    await _until(lambda: h.player().state == "playing")
    player = h.player()
    assert [q.title for q in player.queue] == ["Song 1", "Song 2", "Song 3"]
    assert player.index == 1
    assert player.queue[0].art == album.id
    assert any(isinstance(e, ui.AudioChanged) for e in h.events)  # the source switch shows
    assert any(isinstance(e, ui.PlayerChanged) for e in h.events)

    await h.backend.queue_song(songs[0].id, True)
    assert [q.title for q in h.player().queue] == ["Song 1", "Song 2", "Song 1", "Song 3"]
    await h.backend.queue_album(album.id, False)
    assert len(h.player().queue) == 7

    await h.backend.player_command(ui.PlayerCommand.PLAY_PAUSE)
    assert h.player().state == "paused"
    await h.backend.player_command(ui.PlayerCommand.PLAY_PAUSE)
    assert h.player().state == "playing"
    await h.backend.player_command(ui.PlayerCommand.NEXT)
    assert h.player().index == 2
    await h.backend.player_command(ui.PlayerCommand.PREVIOUS)
    await h.backend.remove_queue_item(h.player().queue[-1].id)
    assert len(h.player().queue) == 6
    await h.backend.play_queue_item(h.player().queue[0].id)
    assert h.player().index == 0
    await h.backend.player_command(ui.PlayerCommand.STOP)
    assert h.player().state == "stopped"
    await h.backend.clear_queue()
    assert h.player().queue == ()


async def test_play_a_single_song(h: Harness) -> None:
    (album,) = h.backend.library().albums
    song = h.backend.album_songs(album.id)[2]
    await h.backend.play_song(song.id)
    await _until(lambda: h.player().state == "playing")
    assert [q.title for q in h.player().queue] == ["Song 3"]


async def test_radio(h: Harness) -> None:
    await h.backend.search_radio("example")
    radio = h.backend.radio()
    assert [s.name for s in radio.results] == ["Example FM"]
    await h.backend.save_station("uuid-1")
    assert [s.id for s in h.backend.radio().saved] == ["uuid-1"]
    await h.backend.play_station("uuid-1")
    await _until(lambda: h.player().state == "playing")
    assert h.player().queue[0].kind == "radio"
    assert h.player().queue[0].title == "Example FM"
    await h.backend.remove_station("uuid-1")
    assert h.backend.radio().saved == ()
    with pytest.raises(ui.LibraryError):
        await h.backend.play_station("nope")


async def test_problems_are_words_for_the_window(h: Harness) -> None:
    with pytest.raises(ui.LibraryError):
        await h.backend.play_album("nope")
    with pytest.raises(ui.LibraryError):
        await h.backend.play_song("nope")
    with pytest.raises(ui.LibraryError):
        await h.backend.add_music_folder(str(h.music / "not a folder"))
    await h.backend.remove_music_folder(str(h.music))
    assert h.backend.library().albums == ()
    await h.backend.rescan_library()
    await h.library.wait_idle()


async def test_without_a_library_or_radio(tmp_path: Path, manual_sleep: ManualSleep) -> None:
    bus = EventBus()
    engine = Engine(FakeBackend([]), bus=bus, sleep=manual_sleep)
    backend = bridge.EngineBackend(engine, SettingsStore(tmp_path / "s.json", bus))
    assert backend.library() == ui.LibrarySnapshot()
    assert backend.radio() == ui.RadioSnapshot()
    assert backend.search_songs("x") == []
    assert backend.library_art("x") is None
    with pytest.raises(ui.LibraryError):
        await backend.add_music_folder(str(tmp_path))
    await backend.search_radio("x")
    await backend.save_station("x")
    await backend.remove_station("x")
    await backend.remove_music_folder("x")
    await backend.rescan_library()
