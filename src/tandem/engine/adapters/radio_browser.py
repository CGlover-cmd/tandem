"""Station search in the Radio Browser directory (https://api.radio-browser.info), over HTTPS.

Sends only the search words, with a generic User-Agent naming Tandem and its version (the
directory asks clients to identify themselves). No account, cookies or identifiers.
"""

from __future__ import annotations

from typing import Any

import aiohttp

from tandem import __version__

API = "https://all.api.radio-browser.info/json/stations/search"
USER_AGENT = f"Tandem/{__version__}"
TIMEOUT = aiohttp.ClientTimeout(total=10)


def search_params(query: str, limit: int) -> dict[str, str]:
    return {
        "name": query,
        "limit": str(limit),
        "hidebroken": "true",
        "order": "clickcount",
        "reverse": "true",
    }


async def search_stations(query: str, limit: int) -> list[dict[str, Any]]:  # pragma: no cover
    async with (
        aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as http,
        http.get(API, params=search_params(query, limit)) as response,
    ):
        response.raise_for_status()
        rows: Any = await response.json(content_type=None)
    if not isinstance(rows, list):
        return []
    items: list[Any] = list(rows)  # pyright: ignore[reportUnknownArgumentType]
    return [row for row in items if isinstance(row, dict)]
