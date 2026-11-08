"""Apple Music catalog search, without an Apple developer account (Phase 6, ADR-0013 note).

Apple's public Search API (https://itunes.apple.com/search) needs no key. Its terms: about 20
calls a minute; artwork and previews may be shown only to promote the item, next to an
official Apple badge that links to it; previews must be credited "courtesy of iTunes" and
never saved. So Tandem shows artwork with Apple's "Listen on Apple Music" badge (fetched from
Apple at run time, never committed) as the way to open each result, plays no previews, and
keeps at most 20 searches in any minute.

Opening a result hands its link to the Apple Music app (`music://`), which plays it there; its
sound then reaches the speakers through the router like any other app's. No library or
playlist access: that needs a MusicKit key (on hold).

Search words and results are personal: never logged.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from tandem.engine.events import Event, EventBus

_LOGGER = logging.getLogger(__name__)

MAX_PER_MINUTE = 20
LIMIT = 30
MAX_QUERY = 100
MAX_ART_CACHE = 120
_HOSTS = ("music.apple.com", "itunes.apple.com", "geo.music.apple.com")
_ART_HOSTS = (".mzstatic.com",)


@dataclass(frozen=True, slots=True)
class CatalogSong:
    id: str
    title: str
    artist: str
    album: str | None
    album_id: str | None
    duration: float | None
    has_art: bool


@dataclass(frozen=True, slots=True)
class CatalogAlbum:
    id: str
    title: str
    artist: str
    year: int | None
    has_art: bool


@dataclass(frozen=True, slots=True)
class CatalogStatus:
    query: str = ""
    searching: bool = False
    songs: tuple[CatalogSong, ...] = ()
    albums: tuple[CatalogAlbum, ...] = ()
    error: str | None = None
    """"unavailable" (no answer) or "busy" (too many searches this minute)."""


@dataclass(frozen=True, slots=True)
class CatalogChanged(Event):
    status: CatalogStatus = field(default_factory=CatalogStatus)


@dataclass(frozen=True, slots=True)
class CatalogArt:
    data: bytes
    mimetype: str


CatalogSearch = Callable[[str, str, int], Awaitable[list[dict[str, Any]]]]
"""Search words, a two-letter country and a limit in; Apple's result rows out."""
FetchImage = Callable[[str], Awaitable[CatalogArt | None]]
OpenLink = Callable[[str], Awaitable[bool]]


def app_link(url: str) -> str | None:
    """An Apple Music web link as a `music://` link for the Apple Music app; None if it isn't
    an Apple link. Apple's tracking parameter (`uo`) is dropped."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.hostname not in _HOSTS:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k != "uo"])
    return urlunsplit(("music", "music.apple.com", parts.path, query, ""))


def large_artwork(url: str) -> str | None:
    """Apple's 100 px artwork link as a 600 px one (the size is part of the file name)."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not (parts.hostname or "").endswith(_ART_HOSTS):
        return None
    return url.replace("100x100bb", "600x600bb")


class AppleCatalog:
    def __init__(
        self,
        bus: EventBus,
        search: CatalogSearch,
        fetch_image: FetchImage,
        open_link: OpenLink,
        *,
        fetch_badge: Callable[[], Awaitable[CatalogArt | None]] | None = None,
        country: str = "us",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._bus = bus
        self._search = search
        self._fetch_image = fetch_image
        self._open_link = open_link
        self._fetch_badge = fetch_badge
        self._badge: CatalogArt | None = None
        self._country = country if len(country) == 2 and country.isalpha() else "us"
        self._clock = clock
        self._calls: deque[float] = deque()
        self._status = CatalogStatus()
        self._attempt = 0
        self._links: dict[str, str] = {}
        self._art_urls: dict[str, str] = {}
        self._art: dict[str, CatalogArt | None] = {}

    @property
    def status(self) -> CatalogStatus:
        return self._status

    async def search(self, text: str) -> None:
        query = " ".join(text.split())[:MAX_QUERY]
        self._attempt += 1
        attempt = self._attempt
        if not query:
            self._set(query="", searching=False, songs=(), albums=(), error=None)
            return
        if not self._allowed():
            self._set(query=query, searching=False, error="busy")
            return
        self._set(query=query, searching=True, error=None)
        try:
            rows = await self._search(query, self._country, LIMIT)
        except Exception as exc:  # offline, Apple refusing (403/429), a bad reply
            _LOGGER.info("Apple Music catalog search failed (%s)", type(exc).__name__)
            if attempt == self._attempt:
                self._set(searching=False, songs=(), albums=(), error="unavailable")
            return
        if attempt != self._attempt:
            return  # the user typed on
        songs, albums = self._results(rows)
        self._set(searching=False, songs=songs, albums=albums, error=None)

    async def open(self, item_id: str) -> bool:
        """Open a song or album in the Apple Music app. False if it's unknown or didn't open."""
        link = self._links.get(item_id)
        if link is None:
            return False
        try:
            return await self._open_link(link)
        except OSError as exc:
            _LOGGER.info("Opening the Apple Music app failed (%s)", type(exc).__name__)
            return False

    async def artwork(self, item_id: str) -> CatalogArt | None:
        """Artwork for a result, fetched from Apple and kept in memory only."""
        if item_id in self._art:
            return self._art[item_id]
        url = self._art_urls.get(item_id)
        art = None
        if url is not None:
            try:
                art = await self._fetch_image(url)
            except Exception as exc:
                _LOGGER.debug("Fetching catalog artwork failed (%s)", type(exc).__name__)
                return None
        while len(self._art) >= MAX_ART_CACHE:
            self._art.pop(next(iter(self._art)))
        self._art[item_id] = art
        return art

    async def badge(self) -> CatalogArt | None:
        """Apple's "Listen on Apple Music" badge, fetched from Apple once and kept in memory."""
        if self._badge is None and self._fetch_badge is not None:
            try:
                self._badge = await self._fetch_badge()
            except Exception as exc:
                _LOGGER.debug("Fetching the Apple Music badge failed (%s)", type(exc).__name__)
        return self._badge

    def _allowed(self) -> bool:
        now = self._clock()
        while self._calls and now - self._calls[0] >= 60:
            self._calls.popleft()
        if len(self._calls) >= MAX_PER_MINUTE:
            return False
        self._calls.append(now)
        return True

    def _results(
        self, rows: list[dict[str, Any]]
    ) -> tuple[tuple[CatalogSong, ...], tuple[CatalogAlbum, ...]]:
        songs: list[CatalogSong] = []
        albums: dict[str, CatalogAlbum] = {}
        for row in rows:
            if row.get("wrapperType") != "track" or row.get("kind") != "song":
                continue
            try:
                song_id = f"s{int(row['trackId'])}"
                title = str(row["trackName"])
                artist = str(row.get("artistName") or "")
            except (KeyError, TypeError, ValueError):
                continue
            link = app_link(str(row.get("trackViewUrl") or ""))
            if link is None:
                continue
            art = large_artwork(str(row.get("artworkUrl100") or ""))
            album_id = None
            if row.get("collectionId") is not None:
                album_id = f"a{row['collectionId']}"
                album_link = app_link(str(row.get("collectionViewUrl") or ""))
                if album_id not in albums and album_link is not None:
                    album_link = _without_track(album_link)
                    albums[album_id] = CatalogAlbum(
                        album_id,
                        str(row.get("collectionName") or title),
                        str(row.get("collectionArtistName") or artist),
                        _year(row.get("releaseDate")),
                        art is not None,
                    )
                    self._links[album_id] = album_link
                    if art is not None:
                        self._art_urls[album_id] = art
            millis = row.get("trackTimeMillis")
            songs.append(
                CatalogSong(
                    song_id,
                    title,
                    artist,
                    str(row.get("collectionName") or "") or None,
                    album_id,
                    float(millis) / 1000 if isinstance(millis, int | float) else None,
                    art is not None,
                )
            )
            self._links[song_id] = link
            if art is not None:
                self._art_urls[song_id] = art
        return tuple(songs), tuple(albums.values())

    def _set(self, **changes: Any) -> None:
        self._status = replace(self._status, **changes)
        self._bus.publish(CatalogChanged(self._status))


def _without_track(link: str) -> str:
    """An album link without the `i=` track part, so the app shows the whole album."""
    parts = urlsplit(link)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k != "i"])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def _year(value: object) -> int | None:
    text = str(value or "")
    return int(text[:4]) if len(text) >= 4 and text[:4].isdigit() else None
