"""Apple's public Search API, artwork, the Apple Music badge, and opening the Apple Music app.

Sends only the search words and a two-letter country, with a generic `Tandem/<version>`
User-Agent. No account, cookies or identifiers. Nothing here is logged.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any, cast

import aiohttp

from tandem import __version__
from tandem.engine.apple_catalog import CatalogArt

SEARCH = "https://itunes.apple.com/search"
BADGE = "https://toolbox.marketingtools.apple.com/api/badges/listen-on-apple-music/badge/{locale}"
USER_AGENT = f"Tandem/{__version__}"
TIMEOUT = aiohttp.ClientTimeout(total=10)
MAX_IMAGE = 2 * 1024 * 1024
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/svg+xml")


def search_params(term: str, country: str, limit: int) -> dict[str, str]:
    return {
        "term": term,
        "media": "music",
        "entity": "song",
        "country": country,
        "limit": str(limit),
    }


def badge_locale(country: str) -> str:
    """Apple's badges come per locale; English for the country is always offered."""
    return f"en-{country.lower()}" if len(country) == 2 else "en-us"


async def search_catalog(
    term: str, country: str, limit: int
) -> list[dict[str, Any]]:  # pragma: no cover
    async with (
        aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as http,
        http.get(SEARCH, params=search_params(term, country, limit)) as response,
    ):
        response.raise_for_status()
        data: Any = await response.json(content_type=None)
    if not isinstance(data, dict):
        return []
    rows: Any = cast(dict[str, Any], data).get("results")
    if not isinstance(rows, list):
        return []
    items: list[Any] = list(rows)  # pyright: ignore[reportUnknownArgumentType]
    return [row for row in items if isinstance(row, dict)]


async def fetch_image(url: str) -> CatalogArt | None:  # pragma: no cover - needs the network
    async with (
        aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as http,
        http.get(url) as response,
    ):
        if response.status != 200:
            return None
        mimetype = response.content_type
        data = await response.content.read(MAX_IMAGE + 1)
    if mimetype not in IMAGE_TYPES or len(data) > MAX_IMAGE:
        return None
    return CatalogArt(data, mimetype)


def badge_fetcher(country: str) -> Callable[[], Awaitable[CatalogArt | None]]:  # pragma: no cover
    async def fetch() -> CatalogArt | None:
        art = await fetch_image(BADGE.format(locale=badge_locale(country)) + "?size=250x83")
        if art is None and country.lower() != "us":
            art = await fetch_image(BADGE.format(locale="en-us") + "?size=250x83")
        return art

    return fetch


async def open_in_apple_music(link: str) -> bool:  # pragma: no cover - opens an app
    """Hand a `music://` link to Windows, which opens it in the Apple Music app."""
    if not link.startswith("music://"):
        return False
    starter: Any = getattr(os, "startfile", None)
    if starter is None:
        return False
    await asyncio.to_thread(starter, link)
    return True
