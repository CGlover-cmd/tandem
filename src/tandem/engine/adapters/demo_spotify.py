"""The demo's invented Spotify (ADR-0019): the Web API, the browser, the sign-in listener and
the secret file that the real `Spotify` talks to, answered from invented playlists, devices
and results (docs/PRIVACY.md). Nothing reaches Spotify and no browser opens; signing in waits
`delay` seconds, then "Spotify" sends the browser back.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

from tandem.engine.spotify import API, AUTHORIZE, TOKEN, HttpReply, SpotifyArt

Sleep = Callable[[float], Awaitable[None]]

# Invented playlists: id, name, owner, track count.
DEMO_PLAYLISTS = (
    ("demo1", "Sunday Morning", "Demo User", 24),
    ("demo2", "Focus Beats", "Demo User", 57),
    ("demo3", "Road Trip Mix", "Example Friend", 31),
)
# Invented Spotify Connect devices: id, name, type, active, restricted.
DEMO_DEVICES = (
    ("demo-dev-1", "Demo Laptop", "Computer", True, False),
    ("demo-dev-2", "Example Phone", "Smartphone", False, False),
    ("demo-dev-3", "Sample Smart TV", "TV", False, True),
)
# Invented search results.
DEMO_TRACKS = (
    ("demo1", "Paper Lanterns", "Example Duo", "Lights", 214_000),
    ("demo2", "Lantern Song", "Sample Singer", "Glow", 187_000),
)
DEMO_ALBUMS = (("demo1", "Lights", "Example Duo", "2022"),)
DEMO_SEARCH_PLAYLISTS = (("demo4", "Lantern Evenings", "Demo Curator", 40),)
_COLOURS = {
    "playlist": ("#1DB954", "#1E3264"),
    "track": ("#E8115B", "#7358FF"),
    "album": ("#F59B23", "#E91429"),
}
_IMAGES = "https://i.scdn.co/image/demo"


def _art(colours: tuple[str, str]) -> bytes:
    start, end = colours
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{start}"/><stop offset="1" stop-color="{end}"/>'
        '</linearGradient></defs><rect width="120" height="120" fill="url(#g)"/></svg>'
    ).encode()


def _common(kind: str, spotify_id: str, name: str) -> dict[str, Any]:
    return {
        "id": spotify_id,
        "uri": f"spotify:{kind}:{spotify_id}",
        "name": name,
        "external_urls": {"spotify": f"https://open.spotify.com/{kind}/{spotify_id}"},
        "images": [{"url": f"{_IMAGES}/{kind}/{spotify_id}", "width": 300}],
    }


def _playlist(spotify_id: str, name: str, owner: str, count: int) -> dict[str, Any]:
    return {
        **_common("playlist", spotify_id, name),
        "owner": {"display_name": owner},
        "items": {"total": count},
    }


def _matches(words: list[str], *texts: str) -> bool:
    hay = " ".join(texts).casefold()
    return bool(words) and all(w in hay for w in words)


class DemoSpotifyWeb:
    """Everything `tandem.engine.spotify.Spotify` is given, invented.

    `played` records (item id, device id) for each play request and `opened` each page the
    browser was asked for ("dashboard" for the developer dashboard), for tests.
    """

    def __init__(self, *, sleep: Sleep = asyncio.sleep, delay: float = 0.6) -> None:
        self._sleep = sleep
        self._delay = delay
        self.saved: dict[str, Any] | None = None
        self.active: str | None = DEMO_DEVICES[0][0]
        self.played: list[tuple[str, str | None]] = []
        self.opened: list[str] = []
        self._listener: _Listener | None = None

    # The secret file

    def read(self) -> dict[str, Any] | None:
        return self.saved

    def write(self, data: dict[str, Any]) -> None:
        self.saved = dict(data)

    # The browser and the sign-in listener

    async def listen(self, path: str) -> _Listener:
        self._listener = _Listener()
        return self._listener

    async def open_url(self, url: str) -> bool:
        if url.startswith(AUTHORIZE):
            state = parse_qs(urlsplit(url).query).get("state", [""])[0]
            listener = self._listener
            if listener is not None:
                asyncio.get_running_loop().create_task(self._send_back(listener, state))
            return True
        parts = urlsplit(url)
        if parts.hostname == "developer.spotify.com":
            self.opened.append("dashboard")
        else:
            kind, _, spotify_id = parts.path.strip("/").partition("/")
            self.opened.append(f"{kind[:1]}:{spotify_id}")
        return True

    async def _send_back(self, listener: _Listener, state: str) -> None:
        await self._sleep(self._delay)  # the user agrees on "Spotify's" page
        listener.answer({"code": "demo-code", "state": state})

    # The Web API

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
        if url == TOKEN:
            return HttpReply(
                200,
                {
                    "access_token": "demo-access",
                    "expires_in": 3600,
                    "refresh_token": "demo-refresh",
                },
            )
        path = url.removeprefix(API)
        params = params or {}
        if (method, path) == ("GET", "/me/playlists"):
            return HttpReply(200, {"items": [_playlist(*p) for p in DEMO_PLAYLISTS]})
        if (method, path) == ("GET", "/me/player/devices"):
            return HttpReply(200, {"devices": self._devices()})
        if (method, path) == ("GET", "/search"):
            return HttpReply(200, self._search(params.get("q", "")))
        if (method, path) == ("PUT", "/me/player/play"):
            return self._play(params.get("device_id"), json or {})
        if (method, path) == ("PUT", "/me/player"):
            device_ids = (json or {}).get("device_ids") or [None]
            self.active = device_ids[0]
            return HttpReply(204)
        return HttpReply(404, {"error": {"status": 404, "message": "Not found"}})

    async def image(self, url: str) -> SpotifyArt | None:
        kind = urlsplit(url).path.split("/")[3:4]
        colours = _COLOURS.get(kind[0] if kind else "", ("#1DB954", "#1E3264"))
        return SpotifyArt(_art(colours), "image/svg+xml")

    async def close(self) -> None:
        return None

    # Internals

    def _devices(self) -> list[dict[str, Any]]:
        return [
            {
                "id": device_id,
                "name": name,
                "type": kind,
                "is_active": device_id == self.active,
                "is_restricted": restricted,
            }
            for device_id, name, kind, _active, restricted in DEMO_DEVICES
        ]

    def _search(self, query: str) -> dict[str, Any]:
        words = query.casefold().split()
        tracks = [
            {
                **_common("track", spotify_id, name),
                "artists": [{"name": artist}],
                "album": {"name": album, "images": [{"url": f"{_IMAGES}/track/{spotify_id}"}]},
                "duration_ms": millis,
            }
            for spotify_id, name, artist, album, millis in DEMO_TRACKS
            if _matches(words, name, artist, album)
        ]
        albums = [
            {
                **_common("album", spotify_id, name),
                "artists": [{"name": artist}],
                "release_date": year,
            }
            for spotify_id, name, artist, year in DEMO_ALBUMS
            if _matches(words, name, artist)
        ]
        playlists = [
            _playlist(*row) for row in DEMO_SEARCH_PLAYLISTS if _matches(words, row[1], row[2])
        ]
        return {
            "tracks": {"items": tracks},
            "albums": {"items": albums},
            "playlists": {"items": playlists},
        }

    def _play(self, device_id: str | None, body: dict[str, Any]) -> HttpReply:
        target = device_id or self.active
        if target is None:
            return HttpReply(404, {"error": {"status": 404, "reason": "NO_ACTIVE_DEVICE"}})
        uri = str(body.get("context_uri") or (body.get("uris") or [""])[0])
        _, kind, spotify_id = [*uri.split(":"), "", ""][:3]
        self.played.append((f"{kind[:1]}:{spotify_id}", device_id))
        self.active = target
        return HttpReply(204)


class _Listener:
    """The one-shot sign-in listener; the demo has no real port."""

    def __init__(self) -> None:
        self._reply: asyncio.Future[dict[str, str]] = asyncio.get_running_loop().create_future()

    @property
    def port(self) -> int:
        return 50000

    def answer(self, query: dict[str, str]) -> None:
        if not self._reply.done():
            self._reply.set_result(query)

    async def wait(self) -> dict[str, str]:
        return await self._reply

    async def close(self) -> None:
        if not self._reply.done():
            self._reply.cancel()
