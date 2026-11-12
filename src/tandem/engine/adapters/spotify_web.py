"""Spotify's Web API over aiohttp, the sign-in's loopback listener, and the system browser.

Nothing here is logged: requests carry tokens, and replies carry playlists and devices.
"""

from __future__ import annotations

import asyncio
import webbrowser
from typing import Any

import aiohttp
from aiohttp import web

from tandem import __version__
from tandem.engine.spotify import HttpReply, SpotifyArt

USER_AGENT = f"Tandem/{__version__}"
TIMEOUT = aiohttp.ClientTimeout(total=15)
MAX_IMAGE = 2 * 1024 * 1024
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")

# The page the browser shows after Spotify sends it back. Plain words, no scripts.
_DONE_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Tandem</title>
<style>body{font:16px system-ui,sans-serif;margin:15vh auto;max-width:28em;
text-align:center}</style>
</head><body><h1>Back to Tandem</h1><p>You can close this tab now.</p></body></html>
"""
_PAGE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
}


class AiohttpSpotifyHttp:  # pragma: no cover - needs the network
    """One HTTP session for Spotify, opened on first use."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
            )
        return self._session

    async def request(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
    ) -> HttpReply:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with self._http().request(
            method, url, headers=headers, params=params, json=json, data=form
        ) as response:
            body: Any = None
            if response.content_type == "application/json":
                try:
                    body = await response.json()
                except ValueError:
                    body = None
            retry = response.headers.get("Retry-After", "")
            return HttpReply(response.status, body, float(retry) if retry.isdigit() else None)

    async def image(self, url: str) -> SpotifyArt | None:
        async with self._http().get(url) as response:
            if response.status != 200:
                return None
            mimetype = response.content_type
            data = await response.content.read(MAX_IMAGE + 1)
        if mimetype not in IMAGE_TYPES or len(data) > MAX_IMAGE:
            return None
        return SpotifyArt(data, mimetype)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()


class LoopbackListener:
    """A one-shot web server on 127.0.0.1 that waits for Spotify to send the browser back."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._result: asyncio.Future[dict[str, str]] = asyncio.get_running_loop().create_future()
        app = web.Application()
        app.router.add_get(path, self._callback)
        self._runner = web.AppRunner(app, access_log=None)
        self._port = 0

    @property
    def port(self) -> int:
        return self._port

    async def start(self) -> None:
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        address: Any = self._runner.addresses[0]
        self._port = int(address[1])

    async def wait(self) -> dict[str, str]:
        return await asyncio.shield(self._result)

    async def close(self) -> None:
        await self._runner.cleanup()

    async def _callback(self, request: web.Request) -> web.StreamResponse:
        if not self._result.done():
            self._result.set_result({k: v for k, v in request.query.items()})
        return web.Response(text=_DONE_PAGE, content_type="text/html", headers=_PAGE_HEADERS)


async def listen(path: str) -> LoopbackListener:
    """Start a listener on any free loopback port. Raises OSError if it can't bind."""
    listener = LoopbackListener(path)
    try:
        await listener.start()
    except BaseException:
        await listener.close()
        raise
    return listener


async def open_in_browser(url: str) -> bool:  # pragma: no cover - opens the browser
    """Open an https link in the user's default browser (the engine checks the host)."""
    if not url.startswith("https://"):
        return False
    return await asyncio.to_thread(webbrowser.open, url)
