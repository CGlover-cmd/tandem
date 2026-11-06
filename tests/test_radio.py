"""Internet radio search and saved stations (Phase 6). Stations are invented."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from tandem.engine.adapters.radio_browser import USER_AGENT, search_params
from tandem.engine.events import EventBus
from tandem.engine.radio import MAX_RESULTS, Radio, RadioChanged, Station, station_from_row


def row(n: int, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "stationuuid": f"uuid-{n}",
        "name": f"Example Station {n}",
        "url": f"http://radio.example/{n}",
        "url_resolved": f"http://stream.radio.example/{n}",
        "codec": "MP3",
        "bitrate": 128,
        "countrycode": "US",
        "tags": "jazz",
        "hls": 0,
    }
    base.update(extra)
    return base


class FakeDirectory:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, int]] = []
        self.fail: BaseException | None = None
        self.gate: asyncio.Event | None = None

    async def __call__(self, query: str, limit: int) -> list[dict[str, Any]]:
        self.calls.append((query, limit))
        if self.gate is not None:
            await self.gate.wait()
        if self.fail is not None:
            raise self.fail
        return self.rows


def test_rows_become_playable_stations_only() -> None:
    station = station_from_row(row(1))
    assert station == Station(
        "uuid-1", "Example Station 1", "http://stream.radio.example/1", "MP3", 128, "US", "jazz"
    )
    assert station_from_row(row(2, codec="AAC")) is None  # the player can't decode it
    assert station_from_row(row(3, hls=1)) is None
    assert station_from_row(row(4, url_resolved="", url="ftp://x")) is None
    assert station_from_row(row(5, name="  ")) is None
    assert station_from_row({"name": "no uuid"}) is None
    assert station_from_row(row(6, bitrate="fast")) is None
    ogg = station_from_row(row(7, codec="ogg", url_resolved=""))
    assert ogg is not None
    assert (ogg.codec, ogg.url) == ("OGG", "http://radio.example/7")


async def test_search_filters_and_dedupes(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    directory = FakeDirectory([row(1), row(1), row(2, codec="AAC"), row(3)])
    bus = EventBus()
    seen: list[RadioChanged] = []
    bus.subscribe(RadioChanged, seen.append)
    radio = Radio(bus, directory, store=None)
    await radio.search("  smooth jazz  ")
    assert directory.calls == [("smooth jazz", MAX_RESULTS * 2)]
    assert [s.id for s in radio.status.results] == ["uuid-1", "uuid-3"]
    assert any(e.status.searching for e in seen)
    assert not radio.status.searching
    assert "smooth" not in caplog.text

    await radio.search("")
    assert radio.status.results == ()


async def test_search_failure_and_stale_replies() -> None:
    directory = FakeDirectory([row(1)])
    radio = Radio(EventBus(), directory, store=None)
    directory.fail = OSError("offline")
    await radio.search("jazz")
    assert radio.status.error == "unavailable"
    directory.fail = None

    # A slow first search must not overwrite a newer one.
    directory.gate = asyncio.Event()
    first = asyncio.create_task(radio.search("first"))
    await asyncio.sleep(0)
    directory.gate.set()
    directory.rows = [row(9)]
    await radio.search("second")
    await first
    assert radio.status.query == "second"
    assert [s.id for s in radio.status.results] == ["uuid-9"]


async def test_saved_stations_persist(tmp_path: Path) -> None:
    store = tmp_path / "radio.json"
    radio = Radio(EventBus(), FakeDirectory([row(1), row(2)]), store=store)
    await radio.load()
    await radio.search("example")
    assert await radio.save("uuid-2")
    assert not await radio.save("uuid-2")  # once
    assert not await radio.save("nope")
    assert json.loads(store.read_text(encoding="utf-8"))["saved"][0]["id"] == "uuid-2"

    again = Radio(EventBus(), FakeDirectory([]), store=store)
    await again.load()
    assert [s.name for s in again.status.saved] == ["Example Station 2"]
    assert again.station("uuid-2") is not None
    await again.remove("uuid-2")
    await again.remove("uuid-2")
    assert again.status.saved == ()

    store.write_text("garbage", encoding="utf-8")
    broken = Radio(EventBus(), FakeDirectory([]), store=store)
    await broken.load()
    assert broken.status.saved == ()


def test_the_request_sends_only_the_search() -> None:
    assert USER_AGENT.startswith("Tandem/")
    params = search_params("jazz", 10)
    assert params == {
        "name": "jazz",
        "limit": "10",
        "hidebroken": "true",
        "order": "clickcount",
        "reverse": "true",
    }
