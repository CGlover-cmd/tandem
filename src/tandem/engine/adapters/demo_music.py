"""The demo's invented music (ADR-0019): albums, radio stations and Apple catalog results that
the real library, radio and catalog read through their usual adapter calls. Every name is
invented (docs/PRIVACY.md); nothing touches the disk or the network, and the "files" play
silence of the right length.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from tandem.engine.apple_catalog import CatalogArt
from tandem.engine.library import FileEntry, LibraryArt, Tags
from tandem.engine.player import Track, TrackKind

DEMO_FOLDER = "Demo Library"  # relative: the same on every system, so the contract is too
# Invented albums: title, artist, year, artwork colours, songs (title, seconds).
DEMO_ALBUMS = (
    (
        "Daybreak",
        "The Example Band",
        2021,
        ("#5B8CFF", "#B36BFF"),
        (("Morning Light", 214), ("Paper Boats", 187), ("Window Seat", 201), ("Low Tide", 240)),
    ),
    (
        "City Hours",
        "Imaginary Orchestra",
        2019,
        ("#2BB673", "#2B7BB6"),
        (("Night Bus", 242), ("Rooftops", 198), ("Last Train", 263)),
    ),
    (
        "Quiet Rooms",
        "Placeholder Trio",
        2023,
        ("#FF8A5B", "#FFC85B"),
        (("Kettle", 176), ("Slow Snow", 305), ("Lamplight", 229), ("Doorstep", 188)),
    ),
)
# Invented stations, as the radio directory would list them.
DEMO_STATIONS: tuple[dict[str, Any], ...] = (
    {
        "stationuuid": "demo-station-1",
        "name": "Example FM Jazz",
        "url_resolved": "https://radio.example/jazz",
        "codec": "MP3",
        "bitrate": 128,
        "countrycode": "US",
        "tags": "jazz",
    },
    {
        "stationuuid": "demo-station-2",
        "name": "Invented Classical Radio",
        "url_resolved": "https://radio.example/classical",
        "codec": "OGG",
        "bitrate": 160,
        "countrycode": "GB",
        "tags": "classical",
    },
    {
        "stationuuid": "demo-station-3",
        "name": "Placeholder Chillout",
        "url_resolved": "https://radio.example/chillout",
        "codec": "MP3",
        "bitrate": 192,
        "countrycode": "DE",
        "tags": "chillout,lounge",
    },
    {
        "stationuuid": "demo-station-4",
        "name": "Sample News Talk",
        "url_resolved": "https://radio.example/news",
        "codec": "MP3",
        "bitrate": 64,
        "countrycode": "CA",
        "tags": "news,talk",
    },
)
# Invented catalog songs: id, title, artist, album id, album, year, seconds.
DEMO_CATALOG = (
    (1000000011, "Harbour Lights", "Sample Singer", 1000000001, "Coastline", 2022, 201),
    (1000000012, "Harbour Lights (Live)", "Sample Singer", 1000000002, "Coastline Live", 2023, 233),
    (1000000021, "Lights Out", "Made-Up Duo", 1000000003, "Night Shift", 2020, 188),
)
_ART_HOST = "https://is1-ssl.mzstatic.com/image/thumb/demo"
_RADIO_SECONDS = 3600.0


def _path(album: str, artist: str, number: int, title: str) -> str:
    return f"{DEMO_FOLDER}/{artist}/{album}/{number:02d} {title}.mp3"


def _tracks() -> Iterable[tuple[str, Tags, tuple[str, str]]]:
    for album, artist, year, colours, songs in DEMO_ALBUMS:
        for number, (title, seconds) in enumerate(songs, start=1):
            tags = Tags(title, artist, album, artist, number, None, year, float(seconds), True)
            yield _path(album, artist, number, title), tags, colours


def artwork_svg(colours: tuple[str, str]) -> bytes:
    start, end = colours
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">'
        '<defs><linearGradient id="g" x1="0" y1="1" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{start}"/><stop offset="1" stop-color="{end}"/>'
        '</linearGradient></defs><rect width="120" height="120" fill="url(#g)"/>'
        '<circle cx="60" cy="60" r="26" fill="white" fill-opacity="0.25"/>'
        '<circle cx="60" cy="60" r="6" fill="white" fill-opacity="0.85"/></svg>'
    ).encode()


class DemoMusic:
    """The adapter calls `MusicLibrary`, `Radio`, `AppleCatalog` and the player make.

    `opened` records the Apple Music links the window opened, for tests.
    """

    def __init__(self) -> None:
        self._files = {path: (tags, colours) for path, tags, colours in _tracks()}
        self.opened: list[str] = []

    # The library

    def list_files(self, folder: str) -> tuple[list[FileEntry], set[str]]:
        if folder != DEMO_FOLDER:
            return [], set()  # another folder: invented, so empty
        return [FileEntry(path, 4_000_000, 0.0) for path in self._files], set()

    def read_tags(self, path: str) -> Tags | None:
        found = self._files.get(path)
        return None if found is None else found[0]

    def read_art(self, path: str) -> LibraryArt | None:
        found = self._files.get(path)
        return None if found is None else LibraryArt(artwork_svg(found[1]), "image/svg+xml")

    def open_track(self, track: Track) -> _Silence:
        if track.kind is TrackKind.RADIO:
            return _Silence(None)
        found = self._files.get(track.location)
        if found is None:
            raise FileNotFoundError("the demo has no such file")
        return _Silence(found[0].duration)

    # The radio directory

    async def search_stations(self, text: str, limit: int) -> list[dict[str, Any]]:
        words = text.casefold().split()
        rows = [
            row
            for row in DEMO_STATIONS
            if all(w in f"{row['name']} {row['tags']}".casefold() for w in words)
        ]
        return rows[:limit]

    # Apple's catalog

    async def search_catalog(self, text: str, country: str, limit: int) -> list[dict[str, Any]]:
        words = text.casefold().split()
        rows: list[dict[str, Any]] = []
        for track_id, title, artist, album_id, album, year, seconds in DEMO_CATALOG:
            if not all(w in f"{title} {artist}".casefold() for w in words):
                continue
            album_url = f"https://music.apple.com/{country}/album/demo/{album_id}"
            rows.append(
                {
                    "wrapperType": "track",
                    "kind": "song",
                    "trackId": track_id,
                    "trackName": title,
                    "artistName": artist,
                    "trackViewUrl": f"{album_url}?i={track_id}",
                    "collectionId": album_id,
                    "collectionName": album,
                    "collectionViewUrl": f"{album_url}?i={track_id}",
                    "releaseDate": f"{year}-01-01T00:00:00Z",
                    "trackTimeMillis": seconds * 1000,
                    "artworkUrl100": f"{_ART_HOST}/{album_id}/100x100bb.jpg",
                }
            )
        return rows[:limit]

    async def fetch_image(self, url: str) -> CatalogArt | None:
        colours = ("#2B7BB6", "#7B2BB6") if "1000000003" in url else ("#FF6B8B", "#FFB36B")
        return CatalogArt(artwork_svg(colours), "image/svg+xml")

    async def open_link(self, link: str) -> bool:
        self.opened.append(link)
        return True

    async def fetch_badge(self) -> CatalogArt | None:
        return None  # the demo is offline: the window shows a text button instead


class _Silence:
    """A decoded "file" or station: silence, `duration` seconds long (radio runs an hour)."""

    def __init__(self, duration: float | None) -> None:
        self._duration = duration
        self._frames = int((duration or _RADIO_SECONDS) * 44_100)

    @property
    def duration(self) -> float | None:
        return self._duration

    def read(self, frames: int) -> bytes:
        frames = min(frames, self._frames)
        self._frames -= frames
        return bytes(frames * 4)

    def close(self) -> None:
        return None
