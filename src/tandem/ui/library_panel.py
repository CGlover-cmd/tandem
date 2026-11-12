"""The Music tab's library, radio and queue, in plain Python (part of `AppController`).

Like `audio_panel`: the page renders `snapshot()` and sends commands, which `register` adds
to the window's command table. Albums travel without their songs; an album's songs and a song
search are sent only while the page shows them, to keep each state message small. Titles,
folders and searches are personal: never logged.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any, Protocol

from tandem.ui.backend import (
    Backend,
    CatalogSnapshot,
    LibrarySnapshot,
    LibrarySong,
    PlayerCommand,
    PlayerSnapshot,
    RadioSnapshot,
    StationSnapshot,
)
from tandem.ui.window_commands import CommandTable, Fields, Handler

_LOGGER = logging.getLogger(__name__)

MAX_SEARCH_TEXT = 100

Runner = Callable[[Coroutine[Any, Any, None]], object]


class FolderPicker(Protocol):
    async def pick_folder(self) -> str | None:
        """Ask for a folder; None if the user cancelled."""
        ...


class LibraryPanel:
    def __init__(
        self,
        backend: Backend,
        run: Runner,
        *,
        on_change: Callable[[], None],
        picker: FolderPicker | None = None,
    ) -> None:
        self._backend = backend
        self._run = run
        self._on_change = on_change
        self._picker = picker
        self.library: LibrarySnapshot = LibrarySnapshot()
        self.radio: RadioSnapshot = RadioSnapshot()
        self.player: PlayerSnapshot = PlayerSnapshot()
        self.catalog: CatalogSnapshot = CatalogSnapshot()
        self.open_album: str | None = None
        self.album_songs: list[LibrarySong] = []
        self.search_text = ""
        self.search_results: list[LibrarySong] = []
        self.picking = False

    def load(self) -> None:
        self.library = self._backend.library()
        self.radio = self._backend.radio()
        self.player = self._backend.player()
        self.catalog = self._backend.catalog()

    def library_changed(self, library: LibrarySnapshot) -> None:
        self.library = library
        if self.open_album is not None:
            if any(a.id == self.open_album for a in library.albums):
                self.album_songs = self._backend.album_songs(self.open_album)
            else:
                self.open_album, self.album_songs = None, []
        if self.search_text:
            self.search_results = self._backend.search_songs(self.search_text)

    def snapshot(self) -> dict[str, Any]:
        library = self.library
        player = self._backend.player()  # with the position as of now
        return {
            "library": {
                "folders": list(library.folders),
                "scanning": library.scanning,
                "scanned": library.scanned,
                "songCount": library.song_count,
                "albums": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "artist": a.artist,
                        "year": a.year,
                        "trackCount": a.track_count,
                        "hasArt": a.has_art,
                    }
                    for a in library.albums
                ],
                "openAlbum": None
                if self.open_album is None
                else {"id": self.open_album, "songs": [_song(s) for s in self.album_songs]},
                "search": {
                    "text": self.search_text,
                    "songs": [_song(s) for s in self.search_results],
                },
                "canPickFolders": self._picker is not None,
                "picking": self.picking,
            },
            "radio": {
                "query": self.radio.query,
                "searching": self.radio.searching,
                "results": [_station(s) for s in self.radio.results],
                "saved": [_station(s) for s in self.radio.saved],
                "error": self.radio.error,
            },
            "catalog": {
                "query": self.catalog.query,
                "searching": self.catalog.searching,
                "error": self.catalog.error,
                "songs": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "artist": s.artist,
                        "album": s.album,
                        "duration": s.duration,
                        "hasArt": s.has_art,
                    }
                    for s in self.catalog.songs
                ],
                "albums": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "artist": a.artist,
                        "year": a.year,
                        "hasArt": a.has_art,
                    }
                    for a in self.catalog.albums
                ],
            },
            "player": {
                "state": player.state,
                "index": player.index,
                "position": round(player.position, 2),
                "duration": player.duration,
                "error": player.error,
                "queue": [
                    {
                        "id": q.id,
                        "title": q.title,
                        "kind": q.kind,
                        "artist": q.artist,
                        "album": q.album,
                        "art": q.art,
                    }
                    for q in player.queue
                ],
            },
        }

    # Commands

    def register(self, table: CommandTable) -> None:
        """The library, radio, catalog and queue commands."""
        b, run = self._backend, self._run

        def add_folder(_f: Fields) -> None:
            if self._picker is not None and not self.picking:
                run(self._pick_folder())

        def remove_folder(f: Fields) -> None:
            folder = f.text("folder")
            if folder is not None:
                run(b.remove_music_folder(folder))

        def open_album(album_id: str) -> None:
            self.open_album = album_id
            self.album_songs = b.album_songs(album_id)
            self._on_change()

        def close_album(_f: Fields) -> None:
            self.open_album, self.album_songs = None, []
            self._on_change()

        def search_library(f: Fields) -> None:
            text = f.text("text")
            if text is not None:
                text = text[:MAX_SEARCH_TEXT]
                self.search_text = text
                self.search_results = b.search_songs(text) if text.strip() else []
                self._on_change()

        def play_album(f: Fields) -> None:
            album_id = f.text("id")
            if album_id is not None:
                run(b.play_album(album_id, f.text("songId")))

        def queue(action: Callable[[str, bool], Coroutine[Any, Any, None]]) -> Handler:
            def handler(f: Fields) -> None:
                item = f.text("id")
                if item is not None:
                    run(action(item, f.flag("next") is True))

            return handler

        def search(action: Callable[[str], Coroutine[Any, Any, None]]) -> Handler:
            def handler(f: Fields) -> None:
                text = f.text("text")
                if text is not None:
                    run(action(text[:MAX_SEARCH_TEXT]))

            return handler

        def plain(action: Callable[[], Coroutine[Any, Any, None]]) -> Handler:
            def handler(_f: Fields) -> None:
                run(action())

            return handler

        def player(f: Fields) -> None:
            command = f.choice(PlayerCommand, "command")
            if command is not None:
                run(b.player_command(command))

        table.on("addMusicFolder", add_folder)
        table.on("removeMusicFolder", remove_folder)
        table.on("rescanLibrary", plain(b.rescan_library))
        table.on_id("openAlbum", open_album)
        table.on("closeAlbum", close_album)
        table.on("searchLibrary", search_library)
        table.on("playAlbum", play_album)
        table.on("queueAlbum", queue(b.queue_album))
        table.on_id("playSong", lambda song_id: run(b.play_song(song_id)))
        table.on("queueSong", queue(b.queue_song))
        table.on("searchRadio", search(b.search_radio))
        table.on_id("playStation", lambda station_id: run(b.play_station(station_id)))
        table.on_id("saveStation", lambda station_id: run(b.save_station(station_id)))
        table.on_id("removeStation", lambda station_id: run(b.remove_station(station_id)))
        table.on("searchCatalog", search(b.search_catalog))
        table.on_id("openInAppleMusic", lambda item_id: run(b.open_in_apple_music(item_id)))
        table.on("player", player)
        table.on_id("playQueueItem", lambda item_id: run(b.play_queue_item(item_id)))
        table.on_id("removeQueueItem", lambda item_id: run(b.remove_queue_item(item_id)))
        table.on("clearQueue", plain(b.clear_queue))

    async def _pick_folder(self) -> None:
        assert self._picker is not None
        self.picking = True
        self._on_change()
        try:
            folder = await self._picker.pick_folder()
        finally:
            self.picking = False
            self._on_change()
        if folder:
            await self._backend.add_music_folder(folder)


def _song(song: LibrarySong) -> dict[str, Any]:
    return {
        "id": song.id,
        "title": song.title,
        "artist": song.artist,
        "album": song.album,
        "albumId": song.album_id,
        "number": song.number,
        "duration": song.duration,
    }


def _station(station: StationSnapshot) -> dict[str, Any]:
    return {
        "id": station.id,
        "name": station.name,
        "codec": station.codec,
        "bitrate": station.bitrate,
        "country": station.country,
        "tags": station.tags,
    }
