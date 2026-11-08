"""The music library, radio and Tandem's player on the real engine (part of `tandem.bridge`).

Mixed into `EngineBackend`, like `bridge_audio`. Playing anything from the library or the radio
switches the audio source to Tandem's player, so it goes out through the outputs chosen in the
Audio panel. Titles, paths and searches are personal: never logged.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from tandem.engine.apple_catalog import AppleCatalog, CatalogArt, CatalogChanged, CatalogStatus
from tandem.engine.events import EventBus
from tandem.engine.library import Album, LibraryChanged, LibraryStatus, LibraryTrack, MusicLibrary
from tandem.engine.player import NewTrack, Player, PlayerChanged, PlayerStatus, TrackKind
from tandem.engine.radio import Radio, RadioChanged, RadioStatus, Station
from tandem.engine.service import AudioSource, Engine
from tandem.ui import backend as ui

GONE = "That isn't in your music library any more."
NO_STATION = "That station isn't in the list any more. Search again."
NO_FOLDER = "Tandem couldn't add that folder."
NO_APPLE_MUSIC = "The Apple Music app didn't open. Make sure it's installed."


class EngineLibrary:
    """The Music tab's library, radio and queue, for `EngineBackend`."""

    _engine: Engine
    _publish: Callable[[ui.BackendEvent], None]

    def _init_library(
        self,
        library: MusicLibrary | None,
        radio: Radio | None,
        catalog: AppleCatalog | None = None,
    ) -> list[Callable[[], None]]:
        self._library = library
        self._radio = radio
        self._catalog = catalog
        bus: EventBus = self._engine.bus
        return [
            bus.subscribe(
                CatalogChanged, lambda e: self._publish(ui.CatalogChanged(_catalog(e.status)))
            ),
            bus.subscribe(
                LibraryChanged, lambda e: self._publish(ui.LibraryChanged(_library(e.status)))
            ),
            bus.subscribe(RadioChanged, lambda e: self._publish(ui.RadioChanged(_radio(e.status)))),
            bus.subscribe(
                PlayerChanged, lambda e: self._publish(ui.PlayerChanged(_player(e.status)))
            ),
        ]

    async def _start_library(self) -> None:
        if self._library is not None:
            await self._library.load()
        if self._radio is not None:
            await self._radio.load()

    async def _stop_library(self) -> None:
        if self._library is not None:
            await self._library.close()

    @property
    def _player_engine(self) -> Player:
        return self._engine.player

    # Reading

    def library(self) -> ui.LibrarySnapshot:
        return _library(self._library.status if self._library else LibraryStatus())

    def album_songs(self, album_id: str) -> list[ui.LibrarySong]:
        album = self._library.album(album_id) if self._library else None
        return [] if album is None else [_song(t, album) for t in album.tracks]

    def search_songs(self, text: str) -> list[ui.LibrarySong]:
        if self._library is None:
            return []
        songs: list[ui.LibrarySong] = []
        for track in self._library.search(text):
            songs.append(_song(track, self._album_of(track)))
        return songs

    def library_art(self, album_id: str) -> ui.MusicArtwork | None:
        art = self._library.artwork(album_id) if self._library else None
        return None if art is None else ui.MusicArtwork(art.data, art.mimetype)

    def radio(self) -> ui.RadioSnapshot:
        return _radio(self._radio.status if self._radio else RadioStatus())

    def player(self) -> ui.PlayerSnapshot:
        return _player(self._player_engine.status)

    # Library commands

    async def add_music_folder(self, folder: str) -> None:
        if self._library is None or not await asyncio.to_thread(Path(folder).is_dir):
            raise ui.LibraryError(NO_FOLDER)
        await self._library.add_folder(folder)

    async def remove_music_folder(self, folder: str) -> None:
        if self._library is not None:
            await self._library.remove_folder(folder)

    async def rescan_library(self) -> None:
        if self._library is not None:
            self._library.rescan()

    async def play_album(self, album_id: str, song_id: str | None = None) -> None:
        album = self._album(album_id)
        start = next((i for i, t in enumerate(album.tracks) if t.id == song_id), 0)
        await self._use_player()
        self._player_engine.play_tracks([_new(t, album) for t in album.tracks], start)

    async def queue_album(self, album_id: str, play_next: bool) -> None:
        album = self._album(album_id)
        self._player_engine.add_tracks([_new(t, album) for t in album.tracks], play_next=play_next)

    async def play_song(self, song_id: str) -> None:
        track = self._track(song_id)
        await self._use_player()
        player = self._player_engine
        added = player.add_tracks([_new(track, self._album_of(track))], play_next=True)
        if added:
            player.play(added[0].id)

    async def queue_song(self, song_id: str, play_next: bool) -> None:
        track = self._track(song_id)
        self._player_engine.add_tracks([_new(track, self._album_of(track))], play_next=play_next)

    # Radio commands

    async def search_radio(self, text: str) -> None:
        if self._radio is not None:
            await self._radio.search(text)

    async def play_station(self, station_id: str) -> None:
        station = self._radio.station(station_id) if self._radio else None
        if station is None:
            raise ui.LibraryError(NO_STATION)
        await self._use_player()
        self._player_engine.play_tracks([_station_track(station)])

    async def save_station(self, station_id: str) -> None:
        if self._radio is not None:
            await self._radio.save(station_id)

    async def remove_station(self, station_id: str) -> None:
        if self._radio is not None:
            await self._radio.remove(station_id)

    # Apple Music's catalog

    def catalog(self) -> ui.CatalogSnapshot:
        return _catalog(self._catalog.status if self._catalog else CatalogStatus())

    async def search_catalog(self, text: str) -> None:
        if self._catalog is not None:
            await self._catalog.search(text)

    async def open_in_apple_music(self, item_id: str) -> None:
        if self._catalog is None or not await self._catalog.open(item_id):
            raise ui.LibraryError(NO_APPLE_MUSIC)

    async def catalog_art(self, item_id: str) -> ui.MusicArtwork | None:
        return _art(await self._catalog.artwork(item_id) if self._catalog else None)

    async def apple_music_badge(self) -> ui.MusicArtwork | None:
        return _art(await self._catalog.badge() if self._catalog else None)

    # The queue

    async def player_command(self, command: ui.PlayerCommand) -> None:
        player = self._player_engine
        if command is ui.PlayerCommand.PLAY_PAUSE:
            if player.status.queue:
                await self._use_player()
            player.toggle()
        elif command is ui.PlayerCommand.NEXT:
            player.next()
        elif command is ui.PlayerCommand.PREVIOUS:
            player.previous()
        else:
            player.stop()

    async def play_queue_item(self, item_id: str) -> None:
        await self._use_player()
        self._player_engine.play(item_id)

    async def remove_queue_item(self, item_id: str) -> None:
        self._player_engine.remove(item_id)

    async def clear_queue(self) -> None:
        self._player_engine.clear()

    # Internals

    async def _use_player(self) -> None:
        """Send the player's sound to the outputs (the Audio panel's source switches too)."""
        if self._engine.audio_source is not AudioSource.PLAYER:
            await self._engine.set_audio_source(AudioSource.PLAYER)
            self._audio_changed()

    def _audio_changed(self) -> None:
        """Republish the Audio panel (`EngineAudio`'s, which comes first in the MRO)."""

    def _album(self, album_id: str) -> Album:
        album = self._library.album(album_id) if self._library else None
        if album is None:
            raise ui.LibraryError(GONE)
        return album

    def _track(self, song_id: str) -> LibraryTrack:
        track = self._library.track(song_id) if self._library else None
        if track is None:
            raise ui.LibraryError(GONE)
        return track

    def _album_of(self, track: LibraryTrack) -> Album | None:
        if self._library is None:
            return None
        return next(
            (a for a in self._library.status.albums if any(t.id == track.id for t in a.tracks)),
            None,
        )


def _library(status: LibraryStatus) -> ui.LibrarySnapshot:
    return ui.LibrarySnapshot(
        folders=status.folders,
        scanning=status.scanning,
        scanned=status.scanned,
        albums=tuple(
            ui.LibraryAlbum(a.id, a.title, a.artist, a.year, len(a.tracks), a.art is not None)
            for a in status.albums
        ),
        song_count=status.track_count,
    )


def _song(track: LibraryTrack, album: Album | None) -> ui.LibrarySong:
    return ui.LibrarySong(
        track.id,
        track.title,
        track.artist or track.album_artist,
        track.album or (album.title if album else None),
        album.id if album else None,
        track.number,
        track.duration,
    )


def _new(track: LibraryTrack, album: Album | None) -> NewTrack:
    return NewTrack(
        TrackKind.FILE,
        track.path,
        track.title,
        track.artist or track.album_artist,
        track.album or (album.title if album else None),
        album.id if album and album.art else None,
    )


def _station_track(station: Station) -> NewTrack:
    return NewTrack(TrackKind.RADIO, station.url, station.name, None, None, None)


def _station(station: Station) -> ui.StationSnapshot:
    return ui.StationSnapshot(
        station.id, station.name, station.codec, station.bitrate, station.country, station.tags
    )


def _radio(status: RadioStatus) -> ui.RadioSnapshot:
    return ui.RadioSnapshot(
        query=status.query,
        searching=status.searching,
        results=tuple(_station(s) for s in status.results),
        saved=tuple(_station(s) for s in status.saved),
        error=status.error,
    )


def _catalog(status: CatalogStatus) -> ui.CatalogSnapshot:
    return ui.CatalogSnapshot(
        query=status.query,
        searching=status.searching,
        songs=tuple(
            ui.CatalogSong(s.id, s.title, s.artist, s.album, s.duration, s.has_art)
            for s in status.songs
        ),
        albums=tuple(
            ui.CatalogAlbum(a.id, a.title, a.artist, a.year, a.has_art) for a in status.albums
        ),
        error=status.error,
    )


def _art(art: CatalogArt | None) -> ui.MusicArtwork | None:
    return None if art is None else ui.MusicArtwork(art.data, art.mimetype)


def _player(status: PlayerStatus) -> ui.PlayerSnapshot:
    return ui.PlayerSnapshot(
        state=status.state.value,
        queue=tuple(
            ui.QueueItem(t.id, t.title, t.kind.value, t.artist, t.album, t.art)
            for t in status.queue
        ),
        index=status.index,
        position=status.position,
        duration=status.duration,
        error=status.error is not None,
    )
