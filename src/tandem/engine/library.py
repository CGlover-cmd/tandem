"""The music library: the audio files in folders the user picks (Phase 6, ADR-0013).

`MusicLibrary` keeps a list of folders, reads each audio file's tags once and caches them in
Tandem's data folder (`library.json`), so a rescan only reads files that are new or changed.
Tracks are grouped into albums for the Music tab. Reading folders and tags is done by
callables from `adapters` (tinytag, the file system), so this module is tested with fakes.

Titles, artists, albums and file paths are personal: shown in the window, never logged. The
cache stays on this PC like the settings file.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable, Iterable, Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from tandem.engine.events import Event, EventBus

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
MAX_FOLDERS = 20
MAX_SEARCH = 100
UNKNOWN_ALBUM = ""  # albums without a tag are named after their folder


@dataclass(frozen=True, slots=True)
class Tags:
    """What a tag reader found in one file."""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    number: int | None = None
    disc: int | None = None
    year: int | None = None
    duration: float | None = None
    has_art: bool = False


@dataclass(frozen=True, slots=True)
class FileEntry:
    """An audio file a folder lister found."""

    path: str
    size: int
    mtime: float


@dataclass(frozen=True, slots=True)
class LibraryTrack:
    id: str
    path: str
    """Personal: never logged."""
    title: str
    artist: str | None
    album: str | None
    album_artist: str | None
    number: int | None
    disc: int | None
    year: int | None
    duration: float | None
    has_art: bool
    size: int
    mtime: float

    @property
    def folder(self) -> str:
        return str(Path(self.path).parent)


@dataclass(frozen=True, slots=True)
class Album:
    id: str
    title: str
    artist: str | None
    year: int | None
    tracks: tuple[LibraryTrack, ...]
    art: str | None = None
    """A file to read artwork from (embedded, or a cover image beside it); None if none."""


@dataclass(frozen=True, slots=True)
class LibraryStatus:
    folders: tuple[str, ...] = ()
    scanning: bool = False
    scanned: int = 0
    """Files looked at so far in the running scan."""
    albums: tuple[Album, ...] = ()
    track_count: int = 0


@dataclass(frozen=True, slots=True)
class LibraryChanged(Event):
    status: LibraryStatus = field(default_factory=LibraryStatus)


@dataclass(frozen=True, slots=True)
class LibraryArt:
    data: bytes
    mimetype: str


FileLister = Callable[[str], tuple[list[FileEntry], set[str]]]
"""Folder in; its audio files (recursively) and the folders among them that hold a cover image
out. Runs on a worker thread."""
TagReader = Callable[[str], Tags | None]
"""Path in; its tags, or None if it can't be read. Runs on a worker thread."""
ArtReader = Callable[[str], LibraryArt | None]
"""A track's path in; embedded artwork or a cover image beside it out."""


def track_id(path: str) -> str:
    return hashlib.sha1(path.casefold().encode(), usedforsecurity=False).hexdigest()[:16]


def album_id(artist: str | None, title: str, folder: str) -> str:
    key = f"{(artist or '').casefold()}\x00{title.casefold()}"
    if not title:  # untagged files: one album per folder
        key += f"\x00{folder.casefold()}"
    return "a" + hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:15]


def build_albums(tracks: Iterable[LibraryTrack], cover_folders: set[str]) -> tuple[Album, ...]:
    groups: dict[str, list[LibraryTrack]] = {}
    for track in tracks:
        title = track.album or UNKNOWN_ALBUM
        artist = track.album_artist or track.artist
        groups.setdefault(album_id(artist, title, track.folder), []).append(track)
    albums: list[Album] = []
    for aid, members in groups.items():
        members.sort(
            key=lambda t: (t.disc or 1, t.number or 10_000, t.title.casefold(), t.path.casefold())
        )
        first = members[0]
        title = first.album or Path(first.folder).name or "Music"
        artists = {t.album_artist or t.artist for t in members} - {None}
        artist = artists.pop() if len(artists) == 1 else first.album_artist
        art = next((t.path for t in members if t.has_art), None)
        if art is None:
            art = next((t.path for t in members if t.folder in cover_folders), None)
        years = [t.year for t in members if t.year]
        albums.append(Album(aid, title, artist, min(years) if years else None, tuple(members), art))
    albums.sort(key=lambda a: ((a.artist or "~").casefold(), a.title.casefold(), a.id))
    return tuple(albums)


class MusicLibrary:
    def __init__(
        self,
        bus: EventBus,
        *,
        store: Path | None,
        list_files: FileLister,
        read_tags: TagReader,
        read_art: ArtReader,
        progress_every: int = 50,
    ) -> None:
        self._bus = bus
        self._store = store
        self._list_files = list_files
        self._read_tags = read_tags
        self._read_art = read_art
        self._progress_every = progress_every
        self._status = LibraryStatus()
        self._tracks: dict[str, LibraryTrack] = {}
        self._covers: set[str] = set()
        self._scan: asyncio.Task[None] | None = None
        self._rescan = False
        self._art_cache: dict[str, LibraryArt | None] = {}

    @property
    def status(self) -> LibraryStatus:
        return self._status

    def album(self, album_id: str) -> Album | None:
        return next((a for a in self._status.albums if a.id == album_id), None)

    def track(self, track_id: str) -> LibraryTrack | None:
        return self._tracks.get(track_id)

    def search(self, text: str, limit: int = MAX_SEARCH) -> list[LibraryTrack]:
        """Songs whose title, artist or album contain every word of `text`."""
        words = text.casefold().split()
        if not words:
            return []
        found: list[LibraryTrack] = []
        for album in self._status.albums:
            for track in album.tracks:
                hay = " ".join(
                    x for x in (track.title, track.artist, track.album, track.album_artist) if x
                ).casefold()
                if all(word in hay for word in words):
                    found.append(track)
                    if len(found) >= limit:
                        return found
        return found

    def artwork(self, album_id: str) -> LibraryArt | None:
        """The album's artwork, read from its files and kept in memory (never written out)."""
        if album_id in self._art_cache:
            return self._art_cache[album_id]
        album = self.album(album_id)
        art = None
        if album is not None and album.art is not None:
            try:
                art = self._read_art(album.art)
            except Exception as exc:
                _LOGGER.debug("Reading album art failed (%s)", type(exc).__name__)
        if len(self._art_cache) >= 64:
            self._art_cache.pop(next(iter(self._art_cache)))
        self._art_cache[album_id] = art
        return art

    # Folders

    async def load(self) -> None:
        """Read the cached index, then look for changes in the background."""
        folders, tracks, covers = await asyncio.to_thread(self._read_store)
        self._tracks = {t.id: t for t in tracks}
        self._covers = covers
        self._set(folders=tuple(folders))
        if folders:
            self.rescan()

    async def add_folder(self, folder: str) -> bool:
        folder = str(Path(folder))
        folders = self._status.folders
        if any(Path(f) == Path(folder) for f in folders) or len(folders) >= MAX_FOLDERS:
            return False
        self._set(folders=(*folders, folder))
        self.rescan()
        return True

    async def remove_folder(self, folder: str) -> None:
        folders = tuple(f for f in self._status.folders if f != folder)
        if folders == self._status.folders:
            return
        self._set(folders=folders)
        self.rescan()

    def rescan(self) -> None:
        if self._scan is not None and not self._scan.done():
            self._rescan = True  # once the running scan ends
            return
        self._scan = asyncio.get_running_loop().create_task(self._scan_loop())

    async def wait_idle(self) -> None:
        """Wait for any running scan (tests and shutdown)."""
        while self._scan is not None and not self._scan.done():
            await asyncio.shield(self._scan)

    async def close(self) -> None:
        if self._scan is not None:
            self._scan.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._scan

    # Scanning

    async def _scan_loop(self) -> None:
        while True:
            self._rescan = False
            await self._scan_once()
            if not self._rescan:
                return

    async def _scan_once(self) -> None:
        loop = asyncio.get_running_loop()
        folders = self._status.folders
        self._set(scanning=True, scanned=0)

        def progress(count: int) -> None:
            loop.call_soon_threadsafe(lambda: self._set(scanned=count))

        try:
            tracks, covers = await asyncio.to_thread(
                self._walk, folders, dict(self._tracks), progress
            )
        except Exception as exc:  # a folder that went away mid-scan, a full disk...
            _LOGGER.warning("The music library scan stopped (%s)", type(exc).__name__)
            self._set(scanning=False)
            return
        self._tracks = {t.id: t for t in tracks}
        self._covers = covers
        self._art_cache.clear()
        self._set(scanning=False)
        try:
            await asyncio.to_thread(self._write_store)
        except OSError as exc:
            _LOGGER.warning("Couldn't save the music library index (%s)", type(exc).__name__)

    def _walk(
        self,
        folders: Sequence[str],
        known: dict[str, LibraryTrack],
        progress: Callable[[int], None],
    ) -> tuple[list[LibraryTrack], set[str]]:
        tracks: dict[str, LibraryTrack] = {}
        covers: set[str] = set()
        seen = 0
        for folder in folders:
            try:
                entries, folder_covers = self._list_files(folder)
            except OSError as exc:
                _LOGGER.info("A music folder couldn't be read (%s)", type(exc).__name__)
                continue
            covers |= folder_covers
            for entry in entries:
                seen += 1
                if seen % self._progress_every == 0:
                    progress(seen)
                tid = track_id(entry.path)
                if tid in tracks:
                    continue
                cached = known.get(tid)
                if cached is not None and (cached.size, cached.mtime) == (entry.size, entry.mtime):
                    tracks[tid] = cached
                    continue
                track = self._read_track(tid, entry)
                if track is not None:
                    tracks[tid] = track
        progress(seen)
        return list(tracks.values()), covers

    def _read_track(self, tid: str, entry: FileEntry) -> LibraryTrack | None:
        try:
            tags = self._read_tags(entry.path) or Tags()
        except Exception as exc:  # a damaged file: list it by name, without tags
            _LOGGER.debug("A file's tags couldn't be read (%s)", type(exc).__name__)
            tags = Tags()
        return LibraryTrack(
            id=tid,
            path=entry.path,
            title=(tags.title or "").strip() or Path(entry.path).stem,
            artist=_clean(tags.artist),
            album=_clean(tags.album),
            album_artist=_clean(tags.album_artist),
            number=tags.number,
            disc=tags.disc,
            year=tags.year,
            duration=tags.duration,
            has_art=tags.has_art,
            size=entry.size,
            mtime=entry.mtime,
        )

    # The cached index

    def _read_store(self) -> tuple[list[str], list[LibraryTrack], set[str]]:
        if self._store is None or not self._store.exists():
            return [], [], set()
        try:
            data: Any = json.loads(self._store.read_text(encoding="utf-8"))
            if data.get("version") != STORE_VERSION:
                return [str(f) for f in data.get("folders", [])], [], set()
            folders = [str(f) for f in data["folders"]][:MAX_FOLDERS]
            tracks = [LibraryTrack(**row) for row in data["tracks"]]
            covers = {str(c) for c in data.get("covers", [])}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            _LOGGER.warning("Ignoring an unreadable music library index (%s)", type(exc).__name__)
            return [], [], set()
        return folders, tracks, covers

    def _write_store(self) -> None:
        if self._store is None:
            return
        data = {
            "version": STORE_VERSION,
            "folders": list(self._status.folders),
            "covers": sorted(self._covers),
            "tracks": [asdict(t) for t in self._tracks.values()],
        }
        self._store.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._store.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._store)

    def _set(self, **changes: Any) -> None:
        status = replace(self._status, **changes)
        # Albums are rebuilt when the folders change and when a scan ends, not on progress.
        if "folders" in changes or changes.get("scanning") is False:
            albums = build_albums(self._visible_tracks(status.folders), self._covers)
            status = replace(status, albums=albums, track_count=sum(len(a.tracks) for a in albums))
        self._status = status
        self._bus.publish(LibraryChanged(status))

    def _visible_tracks(self, folders: Sequence[str]) -> list[LibraryTrack]:
        """Tracks inside the current folders (a removed folder's tracks disappear at once)."""
        roots = [Path(f) for f in folders]
        return [
            t for t in self._tracks.values() if any(_inside(Path(t.path), root) for root in roots)
        ]


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None
