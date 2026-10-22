from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from tandem.ui.app_icons import (
    DRAWN,
    LOOKUP_URL,
    RETRY_MISSING_AFTER,
    URL_PREFIX,
    AppIconStore,
    icon_file,
    is_icon_file,
)

ART = "https://is1-ssl.mzstatic.com/image/thumb/Purple1/v4/aa/bb/cc/AppIcon/512x512bb.jpg"


class FakeHttp:
    """Answers lookups from `listings` (bundle id -> artwork URL) and serves fake JPEGs."""

    def __init__(self, listings: dict[str, str] | None = None) -> None:
        self.listings = listings or {}
        self.lookups: list[dict[str, str]] = []
        self.downloads: list[str] = []
        self.fail_lookup: Exception | None = None
        self.fail_download: Exception | None = None
        self.closed = False

    async def get_json(self, url: str, params: dict[str, str]) -> Any:
        assert url == LOOKUP_URL
        self.lookups.append(params)
        if self.fail_lookup is not None:
            raise self.fail_lookup
        wanted = params["bundleId"].split(",")
        return {
            "resultCount": 0,
            "results": [
                {"bundleId": b, "artworkUrl512": self.listings[b]}
                for b in wanted
                if b in self.listings
            ]
            + ["not a dict"],
        }

    async def get_bytes(self, url: str, limit: int) -> bytes:
        if self.fail_download is not None:
            raise self.fail_download
        self.downloads.append(url)
        return b"\xff\xd8 fake jpeg"

    async def close(self) -> None:
        self.closed = True


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def _store(tmp_path: Path, http: FakeHttp, clock: Clock | None = None, country: str = "us"):
    return AppIconStore(tmp_path / "icons", http, country=country, clock=clock or Clock())


async def test_finds_downloads_and_serves_from_disk(tmp_path: Path) -> None:
    http = FakeHttp({"com.example.video": ART})
    store = _store(tmp_path, http)

    icons = await store.icons(["com.example.video", "com.example.unlisted"])

    name = icon_file("com.example.video")
    assert icons == {"com.example.video": URL_PREFIX + name}
    assert (tmp_path / "icons" / name).read_bytes().startswith(b"\xff\xd8")
    assert http.downloads == [ART.replace("512x512bb.jpg", "256x256bb.jpg")]
    assert is_icon_file(name)
    assert "com.example" not in name  # file names never reveal the app


async def test_cached_icons_and_misses_are_not_asked_again(tmp_path: Path) -> None:
    http = FakeHttp({"com.example.video": ART})
    clock = Clock()
    await _store(tmp_path, http, clock).icons(["com.example.video", "com.example.unlisted"])
    assert len(http.lookups) == 1

    fresh = _store(tmp_path, http, clock)  # a new launch reads the index from disk
    assert await fresh.icons(["com.example.video", "com.example.unlisted"]) == {
        "com.example.video": URL_PREFIX + icon_file("com.example.video")
    }
    assert len(http.lookups) == 1

    clock.now += RETRY_MISSING_AFTER + 1  # a week later, try the missing one again
    await fresh.icons(["com.example.video", "com.example.unlisted"])
    assert http.lookups[-1]["bundleId"] == "com.example.unlisted"


async def test_built_in_apps_use_aliases_or_are_drawn(tmp_path: Path) -> None:
    http = FakeHttp({"com.apple.Music": ART})
    icons = await _store(tmp_path, http).icons(["com.apple.TVMusic", *sorted(DRAWN)])
    assert set(icons) == {"com.apple.TVMusic"}
    assert http.lookups[0]["bundleId"] == "com.apple.Music"  # nothing about drawn apps


async def test_other_countries_fall_back_to_the_us_store(tmp_path: Path) -> None:
    http = FakeHttp()
    await _store(tmp_path, http, country="GB").icons(["com.example.video"])
    assert [p["country"] for p in http.lookups] == ["gb", "us"]


async def test_bad_ids_and_untrusted_artwork_are_ignored(tmp_path: Path) -> None:
    http = FakeHttp(
        {
            "com.example.video": "http://is1-ssl.mzstatic.com/a/512x512bb.jpg",  # not https
            "com.example.music": "https://example.com/a/512x512bb.jpg",  # not Apple's CDN
        }
    )
    icons = await _store(tmp_path, http).icons(
        ["com.example.video", "com.example.music", "../../etc", ""]
    )
    assert icons == {}
    assert http.downloads == []
    assert http.lookups[0]["bundleId"] == "com.example.video,com.example.music"


async def test_network_trouble_leaves_out_icons_and_logs_no_ids(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    http = FakeHttp({"com.example.video": ART})
    http.fail_lookup = OSError("no route to 192.0.2.9")
    store = _store(tmp_path, http)
    assert await store.icons(["com.example.video"]) == {}

    http.fail_lookup = None
    http.fail_download = TimeoutError()
    assert await store.icons(["com.example.video"]) == {}
    assert "OSError" in caplog.text
    assert "com.example" not in caplog.text
    assert "192.0.2.9" not in caplog.text

    http.fail_download = None
    assert await store.icons(["com.example.video"]) != {}  # a failed download is retried


async def test_lookups_are_batched(tmp_path: Path) -> None:
    http = FakeHttp()
    await _store(tmp_path, http).icons([f"com.example.app{n}" for n in range(120)])
    assert [len(p["bundleId"].split(",")) for p in http.lookups] == [50, 50, 20]


async def test_unreadable_index_starts_over(tmp_path: Path) -> None:
    folder = tmp_path / "icons"
    folder.mkdir()
    (folder / "index.json").write_text("{not json", encoding="utf-8")
    http = FakeHttp({"com.example.video": ART})
    assert await _store(tmp_path, http).icons(["com.example.video"]) != {}
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    assert index["com.example.video"]["file"] == icon_file("com.example.video")


async def test_a_deleted_icon_file_is_fetched_again(tmp_path: Path) -> None:
    http = FakeHttp({"com.example.video": ART})
    store = _store(tmp_path, http)
    await store.icons(["com.example.video"])
    (tmp_path / "icons" / icon_file("com.example.video")).unlink()
    assert await store.icons(["com.example.video"]) != {}
    assert len(http.downloads) == 2


async def test_close_closes_the_http_client(tmp_path: Path) -> None:
    http = FakeHttp()
    await _store(tmp_path, http).close()
    assert http.closed
