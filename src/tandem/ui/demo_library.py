"""The music library, radio and player for `DemoBackend`: invented albums and stations only
(docs/PRIVACY.md). Nothing is decoded or played; the queue and transport just change state.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace

from tandem.ui.backend import (
    BackendEvent,
    LibraryAlbum,
    LibraryChanged,
    LibraryError,
    LibrarySnapshot,
    LibrarySong,
    MusicArtwork,
    PlayerChanged,
    PlayerCommand,
    PlayerSnapshot,
    QueueItem,
    RadioChanged,
    RadioSnapshot,
    StationSnapshot,
)

DEMO_FOLDER = "C:\\Music\\Demo Library"
# Invented albums: id, title, artist, year, artwork colours, songs (title, seconds).
DEMO_ALBUMS = (
    (
        "demo-album-1",
        "Daybreak",
        "The Example Band",
        2021,
        ("#5B8CFF", "#B36BFF"),
        (("Morning Light", 214), ("Paper Boats", 187), ("Window Seat", 201), ("Low Tide", 240)),
    ),
    (
        "demo-album-2",
        "City Hours",
        "Imaginary Orchestra",
        2019,
        ("#2BB673", "#2B7BB6"),
        (("Night Bus", 242), ("Rooftops", 198), ("Last Train", 263)),
    ),
    (
        "demo-album-3",
        "Quiet Rooms",
        "Placeholder Trio",
        2023,
        ("#FF8A5B", "#FFC85B"),
        (("Kettle", 176), ("Slow Snow", 305), ("Lamplight", 229), ("Doorstep", 188)),
    ),
)
DEMO_STATIONS = (
    StationSnapshot("demo-station-1", "Example FM Jazz", "MP3", 128, "US", "jazz"),
    StationSnapshot("demo-station-2", "Invented Classical Radio", "OGG", 160, "GB", "classical"),
    StationSnapshot("demo-station-3", "Placeholder Chillout", "MP3", 192, "DE", "chillout,lounge"),
    StationSnapshot("demo-station-4", "Sample News Talk", "MP3", 64, "CA", "news,talk"),
)
GONE = "That isn't in your music library any more."
NO_STATION = "That station isn't in the list any more. Search again."


def _songs(index: int) -> list[LibrarySong]:
    album_id, title, artist, _year, _colours, songs = DEMO_ALBUMS[index]
    return [
        LibrarySong(f"{album_id}-{n}", song, artist, title, album_id, n, float(seconds))
        for n, (song, seconds) in enumerate(songs, start=1)
    ]


def _art(colours: tuple[str, str]) -> bytes:
    start, end = colours
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">'
        '<defs><linearGradient id="g" x1="0" y1="1" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{start}"/><stop offset="1" stop-color="{end}"/>'
        '</linearGradient></defs><rect width="120" height="120" fill="url(#g)"/>'
        '<circle cx="60" cy="60" r="26" fill="white" fill-opacity="0.25"/>'
        '<circle cx="60" cy="60" r="6" fill="white" fill-opacity="0.85"/></svg>'
    ).encode()


class DemoLibrary:
    """Mixed into `DemoBackend`."""

    _publish: Callable[[BackendEvent], None]

    def _init_library(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._library_clock = clock
        self._folders: tuple[str, ...] = (DEMO_FOLDER,)
        self._radio = RadioSnapshot(saved=(DEMO_STATIONS[1],))
        self._player = PlayerSnapshot()
        self._started_at: float | None = None
        self._next_item = 1

    # Reading

    def library(self) -> LibrarySnapshot:
        if not self._folders:
            return LibrarySnapshot()
        albums = tuple(LibraryAlbum(a[0], a[1], a[2], a[3], len(a[5]), True) for a in DEMO_ALBUMS)
        return LibrarySnapshot(
            folders=self._folders,
            albums=albums,
            song_count=sum(a.track_count for a in albums),
        )

    def album_songs(self, album_id: str) -> list[LibrarySong]:
        index = self._album_index(album_id)
        return [] if index is None or not self._folders else _songs(index)

    def search_songs(self, text: str) -> list[LibrarySong]:
        words = text.casefold().split()
        if not words or not self._folders:
            return []
        found: list[LibrarySong] = []
        for index in range(len(DEMO_ALBUMS)):
            for song in _songs(index):
                hay = f"{song.title} {song.artist} {song.album}".casefold()
                if all(word in hay for word in words):
                    found.append(song)
        return found

    def library_art(self, album_id: str) -> MusicArtwork | None:
        index = self._album_index(album_id)
        return None if index is None else MusicArtwork(_art(DEMO_ALBUMS[index][4]), "image/svg+xml")

    def radio(self) -> RadioSnapshot:
        return self._radio

    def player(self) -> PlayerSnapshot:
        player = self._player
        if player.state == "playing" and self._started_at is not None:
            elapsed = self._library_clock() - self._started_at
            limit = player.duration if player.duration is not None else elapsed
            return replace(player, position=min(player.position + elapsed, limit))
        return player

    # Library

    async def add_music_folder(self, folder: str) -> None:
        if folder not in self._folders:
            self._folders = (*self._folders, folder)
            self._publish(LibraryChanged(self.library()))

    async def remove_music_folder(self, folder: str) -> None:
        self._folders = tuple(f for f in self._folders if f != folder)
        self._publish(LibraryChanged(self.library()))

    async def rescan_library(self) -> None:
        self._publish(LibraryChanged(self.library()))

    async def play_album(self, album_id: str, song_id: str | None = None) -> None:
        songs = self._album_songs_or_fail(album_id)
        start = next((i for i, s in enumerate(songs) if s.id == song_id), 0)
        items = tuple(self._item(s) for s in songs)
        self._set_player(PlayerSnapshot(queue=items))
        self._play_index(start)

    async def queue_album(self, album_id: str, play_next: bool) -> None:
        self._insert([self._item(s) for s in self._album_songs_or_fail(album_id)], play_next)

    async def play_song(self, song_id: str) -> None:
        song = self._song(song_id)
        player = self._player
        at = player.index + 1 if player.index is not None else len(player.queue)
        self._insert([self._item(song)], True)
        self._play_index(at)

    async def queue_song(self, song_id: str, play_next: bool) -> None:
        self._insert([self._item(self._song(song_id))], play_next)

    # Radio

    async def search_radio(self, text: str) -> None:
        words = text.casefold().split()
        results = tuple(
            s
            for s in DEMO_STATIONS
            if words and all(w in f"{s.name} {s.tags}".casefold() for w in words)
        )
        self._radio = replace(self._radio, query=text.strip(), results=results, error=None)
        self._publish(RadioChanged(self._radio))

    async def play_station(self, station_id: str) -> None:
        station = next(
            (s for s in (*self._radio.results, *self._radio.saved) if s.id == station_id), None
        )
        if station is None:
            raise LibraryError(NO_STATION)
        item = QueueItem(self._new_id(), station.name, "radio")
        self._set_player(PlayerSnapshot(queue=(item,)))
        self._play_index(0)

    async def save_station(self, station_id: str) -> None:
        station = next((s for s in self._radio.results if s.id == station_id), None)
        if station is not None and station not in self._radio.saved:
            self._radio = replace(self._radio, saved=(*self._radio.saved, station))
            self._publish(RadioChanged(self._radio))

    async def remove_station(self, station_id: str) -> None:
        self._radio = replace(
            self._radio, saved=tuple(s for s in self._radio.saved if s.id != station_id)
        )
        self._publish(RadioChanged(self._radio))

    # The queue

    async def player_command(self, command: PlayerCommand) -> None:
        player = self.player()
        if command is PlayerCommand.PLAY_PAUSE:
            if player.state == "playing":
                self._started_at = None
                self._set_player(replace(player, state="paused"))
            elif player.queue:
                self._play_index(player.index or 0, keep_position=player.state == "paused")
        elif command is PlayerCommand.NEXT:
            if player.index is not None and player.index + 1 < len(player.queue):
                self._play_index(player.index + 1)
            else:
                self._stop()
        elif command is PlayerCommand.PREVIOUS:
            if player.index is not None:
                self._play_index(max(0, player.index - (0 if player.position > 3 else 1)))
        else:
            self._stop()

    async def play_queue_item(self, item_id: str) -> None:
        index = next((i for i, q in enumerate(self._player.queue) if q.id == item_id), None)
        if index is not None:
            self._play_index(index)

    async def remove_queue_item(self, item_id: str) -> None:
        player = self._player
        index = next((i for i, q in enumerate(player.queue) if q.id == item_id), None)
        if index is None:
            return
        queue = player.queue[:index] + player.queue[index + 1 :]
        current = player.index
        if current == index:
            self._started_at = None
            self._set_player(PlayerSnapshot(queue=queue))
            return
        if current is not None and index < current:
            current -= 1
        self._set_player(replace(player, queue=queue, index=current))

    async def clear_queue(self) -> None:
        self._started_at = None
        self._set_player(PlayerSnapshot())

    # Internals

    def _album_index(self, album_id: str) -> int | None:
        return next((i for i, a in enumerate(DEMO_ALBUMS) if a[0] == album_id), None)

    def _album_songs_or_fail(self, album_id: str) -> list[LibrarySong]:
        songs = self.album_songs(album_id)
        if not songs:
            raise LibraryError(GONE)
        return songs

    def _song(self, song_id: str) -> LibrarySong:
        for index in range(len(DEMO_ALBUMS)):
            for song in _songs(index):
                if song.id == song_id:
                    return song
        raise LibraryError(GONE)

    def _new_id(self) -> str:
        self._next_item += 1
        return f"q{self._next_item}"

    def _item(self, song: LibrarySong) -> QueueItem:
        return QueueItem(self._new_id(), song.title, "file", song.artist, song.album, song.album_id)

    def _insert(self, items: list[QueueItem], play_next: bool) -> None:
        player = self._player
        at = len(player.queue)
        if play_next and player.index is not None:
            at = player.index + 1
        queue = player.queue[:at] + tuple(items) + player.queue[at:]
        self._set_player(replace(player, queue=queue))

    def _play_index(self, index: int, *, keep_position: bool = False) -> None:
        player = self._player
        if not 0 <= index < len(player.queue):
            return
        item = player.queue[index]
        duration = None
        if item.kind == "file" and item.art is not None:
            album = self._album_index(item.art)
            if album is not None:
                lengths = dict(DEMO_ALBUMS[album][5])
                duration = float(lengths.get(item.title, 200))
        position = player.position if keep_position else 0.0
        self._started_at = self._library_clock()
        self._set_player(
            replace(player, state="playing", index=index, position=position, duration=duration)
        )

    def _stop(self) -> None:
        self._started_at = None
        self._set_player(replace(self._player, state="stopped", position=0.0))

    def _set_player(self, player: PlayerSnapshot) -> None:
        self._player = player
        self._publish(PlayerChanged(player))
