"""Apple Music catalog search (Phase 6). Songs and links are invented (docs/PRIVACY.md)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from tandem.engine.adapters.itunes_catalog import badge_locale, search_params
from tandem.engine.apple_catalog import (
    MAX_PER_MINUTE,
    AppleCatalog,
    CatalogArt,
    CatalogChanged,
    app_link,
    large_artwork,
)
from tandem.engine.events import EventBus

ART = "https://is1-ssl.mzstatic.com/image/thumb/Music/v4/aa/bb/x.jpg/100x100bb.jpg"


def row(n: int, collection: int = 900, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "wrapperType": "track",
        "kind": "song",
        "trackId": n,
        "trackName": f"Example Song {n}",
        "artistName": "Example Artist",
        "collectionId": collection,
        "collectionName": "Example Album",
        "trackViewUrl": f"https://music.apple.com/us/album/example/{collection}?i={n}&uo=4",
        "collectionViewUrl": f"https://music.apple.com/us/album/example/{collection}?i={n}&uo=4",
        "artworkUrl100": ART,
        "trackTimeMillis": 200_000,
        "releaseDate": "2021-03-04T08:00:00Z",
    }
    base.update(extra)
    return base


class Fakes:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.searches: list[tuple[str, str, int]] = []
        self.fetched: list[str] = []
        self.opened: list[str] = []
        self.fail: BaseException | None = None
        self.gate: asyncio.Event | None = None
        self.now = 0.0

    async def search(self, term: str, country: str, limit: int) -> list[dict[str, Any]]:
        self.searches.append((term, country, limit))
        if self.gate is not None:
            await self.gate.wait()
        if self.fail is not None:
            raise self.fail
        return self.rows

    async def fetch(self, url: str) -> CatalogArt | None:
        self.fetched.append(url)
        return CatalogArt(b"\xff\xd8\xff", "image/jpeg")

    async def open(self, link: str) -> bool:
        self.opened.append(link)
        return True

    async def badge(self) -> CatalogArt | None:
        self.fetched.append("badge")
        return CatalogArt(b"<svg/>", "image/svg+xml")

    def catalog(self, country: str = "gb") -> AppleCatalog:
        return AppleCatalog(
            EventBus(),
            self.search,
            self.fetch,
            self.open,
            fetch_badge=self.badge,
            country=country,
            clock=lambda: self.now,
        )


def test_links_go_to_the_apple_music_app() -> None:
    assert (
        app_link("https://music.apple.com/us/album/x/1?i=2&uo=4")
        == "music://music.apple.com/us/album/x/1?i=2"
    )
    assert (
        app_link("https://itunes.apple.com/us/album/x/1") == "music://music.apple.com/us/album/x/1"
    )
    assert app_link("https://evil.example/album/x") is None
    assert app_link("javascript:alert(1)") is None
    assert large_artwork(ART) is not None
    assert "600x600bb" in (large_artwork(ART) or "")
    assert large_artwork("http://is1-ssl.mzstatic.com/x/100x100bb.jpg") is None  # not https
    assert large_artwork("https://images.example/x.jpg") is None


async def test_search_finds_songs_and_their_albums(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    fakes = Fakes(
        [
            row(1),
            row(2),
            row(3, collection=901, collectionName="Other Album", artworkUrl100=""),
            {"wrapperType": "artist", "artistName": "skip me"},
            row(4, trackViewUrl="https://evil.example/x"),
            {"wrapperType": "track", "kind": "song"},  # no id
        ]
    )
    catalog = fakes.catalog()
    seen: list[CatalogChanged] = []
    catalog._bus.subscribe(CatalogChanged, seen.append)  # pyright: ignore[reportPrivateUsage]
    await catalog.search("  example   song ")
    assert fakes.searches == [("example song", "gb", 30)]
    status = catalog.status
    assert [s.id for s in status.songs] == ["s1", "s2", "s3"]
    assert status.songs[0].duration == 200.0
    assert status.songs[2].has_art is False
    assert [(a.id, a.title, a.year) for a in status.albums] == [
        ("a900", "Example Album", 2021),
        ("a901", "Other Album", 2021),
    ]
    assert any(e.status.searching for e in seen)
    assert "example song" not in caplog.text.casefold()

    assert await catalog.open("s2")
    assert await catalog.open("a900")
    assert fakes.opened == [
        "music://music.apple.com/us/album/example/900?i=2",
        "music://music.apple.com/us/album/example/900",  # the album, not one track
    ]
    assert not await catalog.open("unknown")

    art = await catalog.artwork("s1")
    assert art is not None
    assert await catalog.artwork("s1") == art  # kept in memory
    assert await catalog.artwork("s3") is None  # no artwork: nothing fetched
    assert fakes.fetched == [large_artwork(ART)]
    assert await catalog.badge() is not None
    assert await catalog.badge() is not None
    assert fakes.fetched.count("badge") == 1


async def test_at_most_twenty_searches_a_minute() -> None:
    fakes = Fakes([row(1)])
    catalog = fakes.catalog()
    for n in range(MAX_PER_MINUTE):
        await catalog.search(f"query {n}")
    await catalog.search("one too many")
    assert catalog.status.error == "busy"
    assert len(fakes.searches) == MAX_PER_MINUTE
    fakes.now += 61
    await catalog.search("later")
    assert catalog.status.error is None
    assert len(fakes.searches) == MAX_PER_MINUTE + 1


async def test_failures_and_stale_replies() -> None:
    fakes = Fakes([row(1)])
    catalog = fakes.catalog(country="not a country")
    fakes.fail = OSError("403")
    await catalog.search("x")
    assert catalog.status.error == "unavailable"
    assert fakes.searches[-1][1] == "us"  # a bad country falls back to the US store
    fakes.fail = None

    fakes.gate = asyncio.Event()
    first = asyncio.create_task(catalog.search("first"))
    await asyncio.sleep(0)
    fakes.gate.set()
    await catalog.search("second")
    await first
    assert catalog.status.query == "second"
    await catalog.search("   ")
    assert catalog.status.songs == ()


async def test_opening_or_fetching_can_fail() -> None:
    fakes = Fakes([row(1)])

    async def broken_open(link: str) -> bool:
        raise OSError("no app for music://")

    async def broken_fetch(url: str) -> CatalogArt | None:
        raise OSError("offline")

    catalog = AppleCatalog(EventBus(), fakes.search, broken_fetch, broken_open, fetch_badge=None)
    await catalog.search("x")
    assert not await catalog.open("s1")
    assert await catalog.artwork("s1") is None
    assert await catalog.badge() is None


def test_request_parameters() -> None:
    assert search_params("jazz", "gb", 30) == {
        "term": "jazz",
        "media": "music",
        "entity": "song",
        "country": "gb",
        "limit": "30",
    }
    assert badge_locale("GB") == "en-gb"
    assert badge_locale("") == "en-us"
