"""The music library (Phase 6). Folders, files and tags are invented (docs/PRIVACY.md)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from tandem.engine.events import EventBus
from tandem.engine.library import (
    MAX_FOLDERS,
    FileEntry,
    LibraryArt,
    LibraryChanged,
    MusicLibrary,
    Tags,
    album_id,
    build_albums,
    track_id,
)

ROOT = str(Path("C:/Music"))
DAY = str(Path("C:/Music/The Example Band/Daybreak"))
LOOSE = str(Path("C:/Music/Loose Files"))


def p(folder: str, name: str) -> str:
    return str(Path(folder) / name)


TAGS = {
    p(DAY, "02 Paper Boats.mp3"): Tags(
        "Paper Boats", "The Example Band", "Daybreak", None, 2, 1, 2021, 187.0, False
    ),
    p(DAY, "01 Morning Light.flac"): Tags(
        "Morning Light", "The Example Band", "Daybreak", None, 1, 1, 2021, 214.0, True
    ),
    p(LOOSE, "untitled demo.wav"): None,  # no tags at all
}


class FakeFiles:
    def __init__(self) -> None:
        self.files: dict[str, list[FileEntry]] = {
            ROOT: [FileEntry(path, 1000, 1.0) for path in TAGS],
        }
        self.covers: dict[str, set[str]] = {ROOT: {LOOSE}}
        self.tag_reads: list[str] = []
        self.art_reads: list[str] = []
        self.broken: set[str] = set()

    def list_files(self, folder: str) -> tuple[list[FileEntry], set[str]]:
        if folder not in self.files:
            raise FileNotFoundError(folder)
        return list(self.files[folder]), set(self.covers.get(folder, set()))

    def read_tags(self, path: str) -> Tags | None:
        self.tag_reads.append(path)
        if path in self.broken:
            raise ValueError("damaged file")
        return TAGS.get(path)

    def read_art(self, path: str) -> LibraryArt | None:
        self.art_reads.append(path)
        return LibraryArt(b"\xff\xd8\xff-art", "image/jpeg")


def make(files: FakeFiles, store: Path | None, bus: EventBus | None = None) -> MusicLibrary:
    return MusicLibrary(
        bus or EventBus(),
        store=store,
        list_files=files.list_files,
        read_tags=files.read_tags,
        read_art=files.read_art,
        progress_every=1,
    )


async def test_scans_a_folder_into_albums(tmp_path: Path) -> None:
    files = FakeFiles()
    bus = EventBus()
    seen: list[LibraryChanged] = []
    bus.subscribe(LibraryChanged, seen.append)
    library = make(files, tmp_path / "library.json", bus)
    await library.load()
    assert await library.add_folder(ROOT)
    await library.wait_idle()

    status = library.status
    assert status.folders == (ROOT,)
    assert not status.scanning
    assert status.track_count == 3
    titles = [(a.title, a.artist) for a in status.albums]
    assert titles == [("Daybreak", "The Example Band"), ("Loose Files", None)]  # unknown last
    daybreak = status.albums[0]
    assert [t.title for t in daybreak.tracks] == ["Morning Light", "Paper Boats"]  # by number
    assert daybreak.year == 2021
    assert daybreak.art == p(DAY, "01 Morning Light.flac")  # embedded art
    assert status.albums[1].art == p(LOOSE, "untitled demo.wav")  # a cover in the folder
    assert status.albums[1].tracks[0].title == "untitled demo"  # named after the file
    assert any(e.status.scanning for e in seen)
    assert any(e.status.scanned > 0 for e in seen)


async def test_the_index_is_cached_and_reused(tmp_path: Path) -> None:
    store = tmp_path / "library.json"
    files = FakeFiles()
    library = make(files, store)
    await library.add_folder(ROOT)
    await library.wait_idle()
    assert len(files.tag_reads) == 3
    assert json.loads(store.read_text(encoding="utf-8"))["folders"] == [ROOT]

    # A new session: everything comes from the cache, and only a changed file is read again.
    changed = p(DAY, "02 Paper Boats.mp3")
    files.files[ROOT] = [FileEntry(path, 1000, 2.0 if path == changed else 1.0) for path in TAGS]
    again = FakeFiles()
    again.files = files.files
    second = make(again, store)
    await second.load()
    assert second.status.track_count == 3  # from the cache, before the rescan ends
    await second.wait_idle()
    assert again.tag_reads == [changed]


async def test_folders_can_be_removed_and_are_limited(tmp_path: Path) -> None:
    files = FakeFiles()
    library = make(files, None)
    await library.add_folder(ROOT)
    assert not await library.add_folder(ROOT)  # already there
    await library.wait_idle()
    await library.remove_folder(ROOT)
    assert library.status.albums == ()
    await library.remove_folder("C:/Not There")
    await library.wait_idle()
    for n in range(MAX_FOLDERS):
        await library.add_folder(f"C:/Folder {n}")
    assert not await library.add_folder("C:/One Too Many")
    await library.close()


async def test_missing_folders_and_damaged_files(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    files = FakeFiles()
    files.broken.add(p(DAY, "02 Paper Boats.mp3"))
    library = make(files, None)
    await library.add_folder(ROOT)
    await library.add_folder("C:/Gone")
    await library.wait_idle()
    assert library.status.track_count == 3  # the damaged file is listed by name
    titles = {t.title for a in library.status.albums for t in a.tracks}
    assert "02 Paper Boats" in titles
    assert "Paper Boats" not in caplog.text
    assert "Example" not in caplog.text


async def test_search_and_lookups() -> None:
    files = FakeFiles()
    library = make(files, None)
    await library.add_folder(ROOT)
    await library.wait_idle()
    assert [t.title for t in library.search("example light")] == ["Morning Light"]
    assert [t.title for t in library.search("DAYBREAK")] == ["Morning Light", "Paper Boats"]
    assert library.search("  ") == []
    assert len(library.search("daybreak", limit=1)) == 1
    tid = track_id(p(DAY, "02 Paper Boats.mp3"))
    track = library.track(tid)
    assert track is not None
    assert track.title == "Paper Boats"
    assert library.album("nope") is None


async def test_artwork_is_read_once_and_kept_in_memory() -> None:
    files = FakeFiles()
    library = make(files, None)
    await library.add_folder(ROOT)
    await library.wait_idle()
    daybreak = library.status.albums[0]
    assert library.artwork(daybreak.id) == LibraryArt(b"\xff\xd8\xff-art", "image/jpeg")
    assert library.artwork(daybreak.id) is not None
    assert files.art_reads == [daybreak.art]
    assert library.artwork("missing") is None


async def test_an_unreadable_cache_is_ignored(tmp_path: Path) -> None:
    store = tmp_path / "library.json"
    store.write_text("{not json", encoding="utf-8")
    library = make(FakeFiles(), store)
    await library.load()
    assert library.status.folders == ()
    store.write_text(json.dumps({"version": 99, "folders": [ROOT]}), encoding="utf-8")
    library = make(FakeFiles(), store)
    await library.load()
    assert library.status.folders == (ROOT,)  # folders kept; files read again
    await library.wait_idle()
    assert library.status.track_count == 3


def test_albums_without_tags_are_kept_apart_by_folder() -> None:
    assert album_id(None, "", "C:/A") != album_id(None, "", "C:/B")
    assert album_id("X", "Same", "C:/A") == album_id("x", "same", "C:/B")
    assert build_albums([], set()) == ()
