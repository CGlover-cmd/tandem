"""App icons for the launcher, looked up on the App Store and kept on disk (ADR-0012).

pyatv lists an Apple TV's apps by bundle id and name only, with no icons. Most tvOS apps
share their bundle id with the iPhone app, so Apple's public lookup service
(itunes.apple.com/lookup) finds their icon. We download each icon once, keep it in the UI's
data folder, and the window loads it from Tandem's own loopback server, never from Apple.

Which apps a person has installed is personal: app ids and names are never logged (counts
only), and the lookup can be turned off in Settings.

Built-in apps that aren't on the App Store (Settings, Search and a few more) get icons drawn
by the front end instead; `DRAWN` lists them so we don't ask Apple about them.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

_LOGGER = logging.getLogger(__name__)

LOOKUP_URL = "https://itunes.apple.com/lookup"
URL_PREFIX = "/app-icons/"
BATCH = 50  # bundle ids per lookup request
MAX_ICON_BYTES = 2_000_000
RETRY_MISSING_AFTER = 7 * 24 * 3600.0
REFRESH_AFTER = 30 * 24 * 3600.0

# tvOS apps whose App Store listing is under their iPhone app's bundle id.
ALIASES = {
    "com.apple.TVMusic": "com.apple.Music",
    "com.apple.TVPhotos": "com.apple.mobileslideshow",
    "com.apple.TVWatchList": "com.apple.tv",
}

# Built into tvOS with no App Store listing: the front end draws these.
DRAWN = frozenset(
    {
        "com.apple.TVSettings",
        "com.apple.TVSearch",
        "com.apple.TVAppStore",
        "com.apple.Arcade",
        "com.apple.TVHomeSharing",
    }
)

_BUNDLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-_]{0,199}")
_FILE = re.compile(r"[0-9a-f]{32}\.jpg")


class Http(Protocol):
    async def get_json(self, url: str, params: dict[str, str]) -> Any: ...
    async def get_bytes(self, url: str, limit: int) -> bytes: ...
    async def close(self) -> None: ...


def icon_file(app_id: str) -> str:
    """The cached file's name: a hash, so app ids never appear in file names."""
    return hashlib.sha256(app_id.encode()).hexdigest()[:32] + ".jpg"


def is_icon_file(name: str) -> bool:
    return bool(_FILE.fullmatch(name))


def _artwork_url(result: dict[str, Any]) -> str | None:
    """The 512-pixel artwork, asked for at 256 pixels as a JPEG (enough for a tile)."""
    url = result.get("artworkUrl512") or result.get("artworkUrl100")
    if not isinstance(url, str):
        return None
    parts = urlsplit(url)
    if parts.scheme != "https" or not (parts.hostname or "").endswith(".mzstatic.com"):
        return None
    return re.sub(r"/\d+x\d+bb\.(jpg|png)$", "/256x256bb.jpg", url)


def _results(data: object) -> list[dict[str, Any]]:
    """The `results` list of a lookup response, keeping only well-formed entries."""
    if not isinstance(data, dict):
        return []
    results = cast(dict[str, Any], data).get("results")
    if not isinstance(results, list):
        return []
    return [cast(dict[str, Any], r) for r in cast(list[object], results) if isinstance(r, dict)]


def _entries(raw: object) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(raw, dict):
        return []
    items = cast(dict[object, object], raw).items()
    return [(str(k), cast(dict[str, Any], v)) for k, v in items if isinstance(v, dict)]


class AppIconStore:
    def __init__(
        self,
        folder: Path,
        http: Http,
        *,
        country: str = "us",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._folder = folder
        self._http = http
        self._countries = [country.lower()] + (["us"] if country.lower() != "us" else [])
        self._clock = clock
        self._lock = asyncio.Lock()
        self._index: dict[str, dict[str, Any]] | None = None

    @property
    def folder(self) -> Path:
        return self._folder

    async def close(self) -> None:
        await self._http.close()

    async def icons(self, app_ids: Iterable[str]) -> dict[str, str]:
        """Icon URLs (on Tandem's own server) for the apps that have one, fetching any
        that aren't cached yet. Never raises: an app without an icon is simply left out."""
        wanted = [i for i in dict.fromkeys(app_ids) if _BUNDLE_ID.fullmatch(i) and i not in DRAWN]
        async with self._lock:
            index = self._load()
            now = self._clock()
            stale = [i for i in wanted if self._needs_lookup(index.get(i), now)]
            if stale:
                try:
                    await self._fetch(index, stale, now)
                except Exception as exc:  # network trouble: show what we have
                    _LOGGER.info("Looking up app icons failed (%s)", type(exc).__name__)
                self._save(index)
        found: dict[str, str] = {}
        for app_id in wanted:
            name = (index.get(app_id) or {}).get("file")
            if isinstance(name, str) and (self._folder / name).is_file():
                found[app_id] = URL_PREFIX + name
        return found

    def _needs_lookup(self, entry: dict[str, Any] | None, now: float) -> bool:
        if entry is None:
            return True
        age = now - float(entry.get("checked", 0))
        if entry.get("file") is None:
            return age > RETRY_MISSING_AFTER
        return age > REFRESH_AFTER or not (self._folder / str(entry["file"])).is_file()

    async def _fetch(
        self, index: dict[str, dict[str, Any]], app_ids: list[str], now: float
    ) -> None:
        artwork: dict[str, str] = {}
        remaining: list[str] = list(app_ids)
        for country in self._countries:
            if not remaining:
                break
            for start in range(0, len(remaining), BATCH):
                chunk = remaining[start : start + BATCH]
                by_listing: dict[str, str] = {ALIASES.get(i, i): i for i in chunk}
                data = await self._http.get_json(
                    LOOKUP_URL,
                    {"bundleId": ",".join(by_listing), "country": country, "entity": "software"},
                )
                for result in _results(data):
                    app_id = by_listing.get(str(result.get("bundleId")))
                    url = _artwork_url(result)
                    if app_id is not None and url is not None:
                        artwork[app_id] = url
            remaining = [i for i in remaining if i not in artwork]

        semaphore = asyncio.Semaphore(6)

        async def download(app_id: str, url: str) -> None:
            async with semaphore:
                try:
                    data = await self._http.get_bytes(url, MAX_ICON_BYTES)
                except Exception as exc:
                    _LOGGER.info("An app icon download failed (%s)", type(exc).__name__)
                    return
            name = icon_file(app_id)
            self._write(name, data)
            index[app_id] = {"file": name, "checked": now}

        await asyncio.gather(*(download(i, u) for i, u in artwork.items()))
        for app_id in app_ids:
            if app_id not in artwork:
                index[app_id] = {"file": None, "checked": now}
        _LOGGER.info("App icons: %d found of %d looked up", len(artwork), len(app_ids))

    # Files

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._index is None:
            try:
                raw = json.loads((self._folder / "index.json").read_text(encoding="utf-8"))
                self._index = {key: entry for key, entry in _entries(raw)}
            except (OSError, ValueError):
                self._index = {}
        return self._index

    def _save(self, index: dict[str, dict[str, Any]]) -> None:
        try:
            self._folder.mkdir(parents=True, exist_ok=True)
            self._replace("index.json", json.dumps(index).encode())
        except OSError as exc:
            _LOGGER.warning("Couldn't save the app icon list (%s)", type(exc).__name__)

    def _write(self, name: str, data: bytes) -> None:
        try:
            self._folder.mkdir(parents=True, exist_ok=True)
            self._replace(name, data)
        except OSError as exc:
            _LOGGER.warning("Couldn't save an app icon (%s)", type(exc).__name__)

    def _replace(self, name: str, data: bytes) -> None:
        temp = self._folder / (name + ".tmp")
        temp.write_bytes(data)
        os.replace(temp, self._folder / name)


class AiohttpHttp:
    """`Http` on aiohttp. Images must be JPEG or PNG and no bigger than `limit`."""

    def __init__(self) -> None:
        self._session: Any = None

    def _client(self) -> Any:
        import aiohttp

        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "Tandem (open-source AirPlay sender)"},
            )
        return self._session

    async def get_json(self, url: str, params: dict[str, str]) -> Any:
        async with self._client().get(url, params=params) as response:
            response.raise_for_status()
            return await response.json(content_type=None)

    async def get_bytes(self, url: str, limit: int) -> bytes:
        async with self._client().get(url) as response:
            response.raise_for_status()
            if response.content_type not in ("image/jpeg", "image/png"):
                raise ValueError("not an image")
            # read() returns whatever has arrived so far; collect every chunk to the end.
            data = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                data += chunk
                if len(data) > limit:
                    raise ValueError("image too large")
            expected = response.content_length
            if expected is not None and len(data) != expected:
                raise ValueError("image cut short")
            return bytes(data)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
