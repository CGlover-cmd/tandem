"""The Music tab's library, radio and queue, in plain Python (part of `AppController`).

Like `audio_panel`: the page renders `snapshot()` and sends commands, which `handle` checks
and runs. Albums travel without their songs; an album's songs and a song search are sent
only while the page shows them, to keep each state message small. Titles, folders and
searches are personal: never logged.
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

    def handle(self, kind: str, command: dict[str, Any]) -> bool:
        """Run a library, radio or queue command. False if `kind` isn't one of them."""
        b = self._backend
        item = command.get("id")
        has_id = isinstance(item, str)
        play_next = command.get("next") is True
        if kind == "addMusicFolder":
            if self._picker is not None and not self.picking:
                self._run(self._pick_folder())
        elif kind == "removeMusicFolder" and isinstance(command.get("folder"), str):
            self._run(b.remove_music_folder(command["folder"]))
        elif kind == "rescanLibrary":
            self._run(b.rescan_library())
        elif kind == "openAlbum" and has_id:
            self.open_album = item
            self.album_songs = b.album_songs(item)
            self._on_change()
        elif kind == "closeAlbum":
            self.open_album, self.album_songs = None, []
            self._on_change()
        elif kind == "searchLibrary" and isinstance(command.get("text"), str):
            text = command["text"][:MAX_SEARCH_TEXT]
            self.search_text = text
            self.search_results = b.search_songs(text) if text.strip() else []
            self._on_change()
        elif kind == "playAlbum" and has_id:
            song = command.get("songId")
            self._run(b.play_album(item, song if isinstance(song, str) else None))
        elif kind == "queueAlbum" and has_id:
            self._run(b.queue_album(item, play_next))
        elif kind == "playSong" and has_id:
            self._run(b.play_song(item))
        elif kind == "queueSong" and has_id:
            self._run(b.queue_song(item, play_next))
        elif kind == "searchRadio" and isinstance(command.get("text"), str):
            self._run(b.search_radio(command["text"][:MAX_SEARCH_TEXT]))
        elif kind == "playStation" and has_id:
            self._run(b.play_station(item))
        elif kind == "saveStation" and has_id:
            self._run(b.save_station(item))
        elif kind == "removeStation" and has_id:
            self._run(b.remove_station(item))
        elif kind == "searchCatalog" and isinstance(command.get("text"), str):
            self._run(b.search_catalog(command["text"][:MAX_SEARCH_TEXT]))
        elif kind == "openInAppleMusic" and has_id:
            self._run(b.open_in_apple_music(item))
        elif kind == "player":
            try:
                action = PlayerCommand(command.get("command"))
            except ValueError:
                return True
            self._run(b.player_command(action))
        elif kind == "playQueueItem" and has_id:
            self._run(b.play_queue_item(item))
        elif kind == "removeQueueItem" and has_id:
            self._run(b.remove_queue_item(item))
        elif kind == "clearQueue":
            self._run(b.clear_queue())
        else:
            return False
        return True

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
