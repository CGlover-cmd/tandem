"""Internet radio: station search and saved stations (Phase 6, ADR-0013).

Search goes to the Radio Browser directory (https://www.radio-browser.info), a free public
service, through a `StationSearch` callable from `adapters` (aiohttp), so this module is
tested with fakes. Only the search words are sent, with a generic "Tandem/<version>"
User-Agent: no account, no identifiers. Saved stations live in Tandem's data folder.

Tandem's player decodes MP3 and Ogg streams (miniaudio), so other codecs are left out.
Search words are personal: never logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from tandem.engine.events import Event, EventBus

_LOGGER = logging.getLogger(__name__)

PLAYABLE_CODECS = frozenset({"MP3", "OGG"})
MAX_RESULTS = 40
MAX_SAVED = 100
MAX_QUERY = 100


@dataclass(frozen=True, slots=True)
class Station:
    id: str
    """Radio Browser's station uuid."""
    name: str
    url: str
    codec: str = ""
    bitrate: int = 0
    country: str = ""
    """A two-letter country code, if the directory knows it."""
    tags: str = ""


@dataclass(frozen=True, slots=True)
class RadioStatus:
    query: str = ""
    searching: bool = False
    results: tuple[Station, ...] = ()
    error: str | None = None
    """"unavailable" when the directory couldn't be reached."""
    saved: tuple[Station, ...] = ()


@dataclass(frozen=True, slots=True)
class RadioChanged(Event):
    status: RadioStatus = field(default_factory=RadioStatus)


StationSearch = Callable[[str, int], Awaitable[list[dict[str, Any]]]]
"""Search words and a limit in; the directory's station rows out."""


def station_from_row(row: dict[str, Any]) -> Station | None:
    """A playable station from one Radio Browser row; None if it can't be played here."""
    try:
        uuid = str(row["stationuuid"])
        name = str(row.get("name") or "").strip()
        url = str(row.get("url_resolved") or row.get("url") or "").strip()
        codec = str(row.get("codec") or "").upper()
        bitrate = int(row.get("bitrate") or 0)
    except (KeyError, TypeError, ValueError):
        return None
    if not (uuid and name and url.startswith(("http://", "https://"))):
        return None
    if codec not in PLAYABLE_CODECS or row.get("hls") in (1, "1", True):
        return None
    return Station(
        uuid,
        name[:120],
        url,
        codec,
        bitrate,
        str(row.get("countrycode") or "")[:2],
        str(row.get("tags") or "")[:200],
    )


class Radio:
    def __init__(self, bus: EventBus, search: StationSearch, *, store: Path | None) -> None:
        self._bus = bus
        self._search = search
        self._store = store
        self._status = RadioStatus()
        self._attempt = 0

    @property
    def status(self) -> RadioStatus:
        return self._status

    def station(self, station_id: str) -> Station | None:
        for station in (*self._status.results, *self._status.saved):
            if station.id == station_id:
                return station
        return None

    async def load(self) -> None:
        saved = await asyncio.to_thread(self._read_store)
        self._set(saved=tuple(saved))

    async def search(self, query: str) -> None:
        query = query.strip()[:MAX_QUERY]
        self._attempt += 1
        attempt = self._attempt
        if not query:
            self._set(query="", searching=False, results=(), error=None)
            return
        self._set(query=query, searching=True, error=None)
        try:
            rows = await self._search(query, MAX_RESULTS * 2)
        except Exception as exc:  # offline, the directory down, a bad reply
            _LOGGER.info("Radio search failed (%s)", type(exc).__name__)
            if attempt == self._attempt:
                self._set(searching=False, results=(), error="unavailable")
            return
        if attempt != self._attempt:
            return  # the user typed on
        stations: list[Station] = []
        seen: set[str] = set()
        for row in rows:
            station = station_from_row(row)
            if station is not None and station.id not in seen:
                seen.add(station.id)
                stations.append(station)
        self._set(searching=False, results=tuple(stations[:MAX_RESULTS]), error=None)

    async def save(self, station_id: str) -> bool:
        station = self.station(station_id)
        saved = self._status.saved
        if station is None or any(s.id == station_id for s in saved) or len(saved) >= MAX_SAVED:
            return False
        self._set(saved=(*saved, station))
        await self._write()
        return True

    async def remove(self, station_id: str) -> None:
        saved = tuple(s for s in self._status.saved if s.id != station_id)
        if saved != self._status.saved:
            self._set(saved=saved)
            await self._write()

    async def _write(self) -> None:
        try:
            await asyncio.to_thread(self._write_store, self._status.saved)
        except OSError as exc:
            _LOGGER.warning("Couldn't save the radio stations (%s)", type(exc).__name__)

    def _read_store(self) -> list[Station]:
        if self._store is None or not self._store.exists():
            return []
        try:
            data: Any = json.loads(self._store.read_text(encoding="utf-8"))
            return [Station(**row) for row in data["saved"]][:MAX_SAVED]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            _LOGGER.warning("Ignoring an unreadable radio stations file (%s)", type(exc).__name__)
            return []

    def _write_store(self, saved: tuple[Station, ...]) -> None:
        if self._store is None:
            return
        self._store.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._store.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"saved": [asdict(s) for s in saved]}, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self._store)

    def _set(self, **changes: Any) -> None:
        self._status = replace(self._status, **changes)
        self._bus.publish(RadioChanged(self._status))
