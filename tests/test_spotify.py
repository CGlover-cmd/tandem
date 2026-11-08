"""Spotify as a Web API remote (Phase 6, ADR-0018). Every id, name and token is invented."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from tandem.engine.events import EventBus
from tandem.engine.spotify import (
    API,
    DASHBOARD,
    REDIRECT_URI,
    SEARCH_LIMIT,
    TOKEN,
    HttpReply,
    ItemKind,
    Spotify,
    SpotifyArt,
    SpotifyChanged,
    SpotifyErrorCode,
    SpotifyState,
    authorize_url,
    code_challenge,
    pick_image,
    safe_link,
    valid_client_id,
)
from tandem.engine.vault import VaultError

CLIENT = "a" * 32  # an invented Client ID
OTHER_CLIENT = "b" * 32
ART = "https://i.scdn.co/image/ab67616d00001e02aaaa"
PORT = 54321

Route = HttpReply | Callable[[dict[str, Any]], HttpReply]


def playlist(n: int, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": f"pl{n}",
        "uri": f"spotify:playlist:pl{n}",
        "name": f"Example Playlist {n}",
        "owner": {"display_name": "Demo Owner"},
        "images": [{"url": ART, "width": 300, "height": 300}],
        "items": {"total": 10 + n},
        "external_urls": {"spotify": f"https://open.spotify.com/playlist/pl{n}"},
    }
    row.update(extra)
    return row


DEVICES = {
    "devices": [
        {"id": "dev1", "name": "Example Laptop", "type": "Computer", "is_active": True},
        {"id": "dev2", "name": "Example Phone", "type": "Smartphone", "is_active": False},
        {"id": None, "name": "Hidden Device", "type": "TV"},
        {"id": "dev3", "name": "Sample TV", "type": "TV", "is_restricted": True},
    ]
}
SEARCH = {
    "tracks": {
        "items": [
            {
                "id": "tr1",
                "uri": "spotify:track:tr1",
                "name": "Invented Song",
                "artists": [{"name": "Example Artist"}, {"name": "Guest"}],
                "album": {"name": "Example Album", "images": [{"url": ART, "width": 64}]},
                "duration_ms": 201_000,
                "external_urls": {"spotify": "https://open.spotify.com/track/tr1"},
            },
            None,
            {"id": "bad", "uri": "spotify:album:bad", "name": "Wrong kind"},
        ]
    },
    "albums": {
        "items": [
            {
                "id": "al1",
                "uri": "spotify:album:al1",
                "name": "Example Album",
                "artists": [{"name": "Example Artist"}],
                "release_date": "2021-05-01",
                "images": [],
            }
        ]
    },
    "playlists": {"items": [None, playlist(9, items=None, tracks={"total": 4})]},
}


class FakeHttp:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.routes: dict[tuple[str, str], list[Route]] = {}
        self.fail: BaseException | None = None
        self.images: list[str] = []
        self.closed = False
        self.token_count = 0
        self.on(
            "POST",
            TOKEN,
            lambda call: self._token(call),
        )
        self.on("GET", "/me/playlists", HttpReply(200, {"items": [playlist(1), None]}))
        self.on("GET", "/me/player/devices", HttpReply(200, DEVICES))

    def _token(self, call: dict[str, Any]) -> HttpReply:
        self.token_count += 1
        n = self.token_count
        return HttpReply(
            200, {"access_token": f"access-{n}", "expires_in": 3600, "refresh_token": "refresh-1"}
        )

    def on(self, method: str, path: str, *replies: Route) -> None:
        url = path if path.startswith("https://") else API + path
        self.routes[(method, url)] = list(replies)

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
        call = {"method": method, "url": url, "token": token, "params": params}
        call |= {"json": json, "form": form}
        self.calls.append(call)
        if self.fail is not None:
            raise self.fail
        replies = self.routes.get((method, url))
        if not replies:
            return HttpReply(204)
        reply = replies[0] if len(replies) == 1 else replies.pop(0)
        return reply(call) if callable(reply) else reply

    def made(self, method: str, path: str) -> list[dict[str, Any]]:
        url = path if path.startswith("https://") else API + path
        return [c for c in self.calls if c["method"] == method and c["url"] == url]

    async def image(self, url: str) -> SpotifyArt | None:
        self.images.append(url)
        return SpotifyArt(b"\xff\xd8\xff", "image/jpeg")

    async def close(self) -> None:
        self.closed = True


class FakeListener:
    def __init__(self) -> None:
        self.result: asyncio.Future[dict[str, str]] = asyncio.get_running_loop().create_future()
        self.closed = False

    @property
    def port(self) -> int:
        return PORT

    async def wait(self) -> dict[str, str]:
        return await asyncio.shield(self.result)

    async def close(self) -> None:
        self.closed = True


class FakeFile:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = data
        self.fail_read = False
        self.writes = 0

    def read(self) -> dict[str, Any] | None:
        if self.fail_read:
            raise VaultError("another user's file")
        return None if self.data is None else dict(self.data)

    def write(self, data: dict[str, Any]) -> None:
        self.writes += 1
        self.data = dict(data)


class Browser:
    """Opens URLs; on Spotify's sign-in page it answers as `answer` says."""

    def __init__(self) -> None:
        self.opened: list[str] = []
        self.answer = "approve"
        self.listeners: list[FakeListener] = []
        self.works = True

    async def open(self, url: str) -> bool:
        self.opened.append(url)
        if not self.works:
            return False
        if url.startswith("https://accounts.spotify.com/authorize"):
            query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
            reply = {
                "approve": {"code": "code-1", "state": query["state"]},
                "deny": {"error": "access_denied", "state": query["state"]},
                "broken": {"error": "server_error", "state": query["state"]},
                "wrong_state": {"code": "code-1", "state": "not-the-same"},
            }.get(self.answer)
            if reply is not None:
                self.listeners[-1].result.set_result(reply)
        return True

    async def listen(self, path: str) -> FakeListener:
        assert path == "/callback"
        if self.answer == "busy":
            raise OSError("no port")
        listener = FakeListener()
        self.listeners.append(listener)
        return listener


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class Rig:
    def __init__(self, saved: dict[str, Any] | None = None, timeout: float = 5.0) -> None:
        self.http = FakeHttp()
        self.file = FakeFile(saved)
        self.browser = Browser()
        self.clock = Clock()
        self.bus = EventBus()
        self.events: list[SpotifyChanged] = []
        self.bus.subscribe(SpotifyChanged, self.events.append)
        self.spotify = Spotify(
            self.bus,
            self.http,
            self.file,
            self.browser.open,
            self.browser.listen,
            clock=self.clock,
            sign_in_timeout=timeout,
        )


async def signed_in() -> Rig:
    rig = Rig({"client_id": CLIENT, "refresh_token": "refresh-0"})
    await rig.spotify.load()
    assert rig.spotify.status.state is SpotifyState.SIGNED_IN
    return rig


# Helpers


def test_client_id_must_be_32_hex_characters() -> None:
    assert valid_client_id(f"  {CLIENT.upper()} ") == CLIENT
    assert valid_client_id("0123456789ABCDEF" * 2) == "0123456789abcdef" * 2
    assert valid_client_id("abc") is None
    assert valid_client_id(CLIENT[:-1] + "g") is None


def test_code_challenge_matches_rfc_7636() -> None:
    # The example from RFC 7636, appendix B (public test values, not secrets).
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"  # pragma: allowlist secret
    challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"  # pragma: allowlist secret
    assert code_challenge(verifier) == challenge


def test_authorize_url_asks_for_pkce_and_only_the_remote_scopes() -> None:
    url = authorize_url(CLIENT, "http://127.0.0.1:5000/callback", "challenge", "state-1")
    query = parse_qs(urlsplit(url).query)
    assert query["client_id"] == [CLIENT]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["http://127.0.0.1:5000/callback"]
    assert set(query["scope"][0].split()) == {
        "playlist-read-private",
        "playlist-read-collaborative",
        "user-read-playback-state",
        "user-modify-playback-state",
    }
    assert REDIRECT_URI == "http://127.0.0.1/callback"


def test_links_and_images_only_from_spotify() -> None:
    assert safe_link("https://open.spotify.com/track/x") is not None
    assert safe_link("http://open.spotify.com/track/x") is None
    assert safe_link("https://example.com/track/x") is None
    assert pick_image("nope") is None
    images = [
        {"url": "https://example.com/a.jpg", "width": 300},
        {"url": "https://i.scdn.co/image/big", "width": 640},
        {"url": "https://mosaic.scdn.co/300/x", "width": 300},
        {"url": 3},
        "junk",
    ]
    assert pick_image(images) == "https://mosaic.scdn.co/300/x"
    assert pick_image([{"url": "https://image-cdn-ak.spotifycdn.com/i/x"}]) is not None


# Setup and sign-in


async def test_full_setup_and_sign_in() -> None:
    rig = Rig()
    await rig.spotify.load()
    assert rig.spotify.status.state is SpotifyState.NOT_SET_UP
    assert await rig.spotify.set_client_id(CLIENT)
    assert rig.spotify.status.state is SpotifyState.SIGNED_OUT
    assert rig.file.data == {"client_id": CLIENT}

    await rig.spotify.sign_in()

    status = rig.spotify.status
    assert status.state is SpotifyState.SIGNED_IN
    assert status.error is None
    assert SpotifyState.SIGNING_IN in [e.status.state for e in rig.events]
    assert rig.browser.listeners[-1].closed
    authorize = parse_qs(urlsplit(rig.browser.opened[0]).query)
    assert authorize["redirect_uri"] == [f"http://127.0.0.1:{PORT}/callback"]
    exchange = rig.http.made("POST", TOKEN)[0]["form"]
    assert exchange["grant_type"] == "authorization_code"
    assert exchange["code"] == "code-1"
    assert exchange["client_id"] == CLIENT
    assert exchange["redirect_uri"] == f"http://127.0.0.1:{PORT}/callback"
    assert code_challenge(exchange["code_verifier"]) == authorize["code_challenge"][0]
    assert rig.file.data == {"client_id": CLIENT, "refresh_token": "refresh-1"}
    # The lists came straight after.
    assert [p.title for p in status.playlists] == ["Example Playlist 1"]
    assert status.playlists[0].count == 11
    assert [d.id for d in status.devices] == ["dev1", "dev2", "dev3"]
    assert status.devices[0].kind == "computer"
    assert status.devices[0].active
    assert status.devices[2].restricted
    assert rig.http.made("GET", "/me/playlists")[0]["token"] == "access-1"


async def test_saved_sign_in_loads_without_a_browser() -> None:
    rig = await signed_in()
    assert rig.browser.opened == []
    refresh = rig.http.made("POST", TOKEN)[0]["form"]
    assert refresh == {
        "grant_type": "refresh_token",
        "refresh_token": "refresh-0",
        "client_id": CLIENT,
    }
    assert rig.file.data == {"client_id": CLIENT, "refresh_token": "refresh-1"}  # rotated


async def test_saved_client_id_without_sign_in() -> None:
    rig = Rig({"client_id": CLIENT})
    await rig.spotify.load()
    assert rig.spotify.status.state is SpotifyState.SIGNED_OUT
    assert rig.http.calls == []


async def test_unreadable_vault_is_left_alone() -> None:
    rig = Rig({"client_id": CLIENT})
    rig.file.fail_read = True
    await rig.spotify.load()
    assert rig.spotify.status.state is SpotifyState.NOT_SET_UP
    assert rig.spotify.status.error is SpotifyErrorCode.VAULT
    assert rig.file.writes == 0


async def test_bad_client_id_is_refused() -> None:
    rig = Rig()
    assert not await rig.spotify.set_client_id("not a client id")
    assert rig.spotify.status.error is SpotifyErrorCode.INVALID_CLIENT_ID
    assert rig.file.writes == 0
    await rig.spotify.sign_in()  # nothing to sign in with
    assert rig.browser.opened == []


async def test_new_client_id_signs_out() -> None:
    rig = await signed_in()
    assert await rig.spotify.set_client_id(CLIENT)  # the same one: still signed in
    assert rig.spotify.status.state is SpotifyState.SIGNED_IN
    assert await rig.spotify.set_client_id(OTHER_CLIENT)
    assert rig.spotify.status.state is SpotifyState.SIGNED_OUT
    assert rig.spotify.status.playlists == ()
    assert rig.file.data == {"client_id": OTHER_CLIENT}


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        ("deny", SpotifyErrorCode.SIGN_IN_DENIED),
        ("broken", SpotifyErrorCode.SIGN_IN_FAILED),
        ("wrong_state", SpotifyErrorCode.SIGN_IN_FAILED),
        ("busy", SpotifyErrorCode.PORT_BUSY),
    ],
)
async def test_sign_in_that_does_not_finish(answer: str, error: SpotifyErrorCode) -> None:
    rig = Rig({"client_id": CLIENT})
    await rig.spotify.load()
    rig.browser.answer = answer
    await rig.spotify.sign_in()
    assert rig.spotify.status.state is SpotifyState.SIGNED_OUT
    assert rig.spotify.status.error is error
    assert rig.http.made("POST", TOKEN) == []
    assert all(listener.closed for listener in rig.browser.listeners)


async def test_sign_in_times_out() -> None:
    rig = Rig({"client_id": CLIENT}, timeout=0.01)
    await rig.spotify.load()
    rig.browser.answer = "never"
    await rig.spotify.sign_in()
    assert rig.spotify.status.error is SpotifyErrorCode.SIGN_IN_TIMEOUT
    assert rig.spotify.status.state is SpotifyState.SIGNED_OUT
    assert rig.browser.listeners[-1].closed


async def test_sign_in_when_the_browser_does_not_open() -> None:
    rig = Rig({"client_id": CLIENT})
    await rig.spotify.load()
    rig.browser.works = False
    await rig.spotify.sign_in()
    assert rig.spotify.status.error is SpotifyErrorCode.SIGN_IN_FAILED


async def test_cancel_sign_in() -> None:
    rig = Rig({"client_id": CLIENT})
    await rig.spotify.load()
    rig.browser.answer = "never"
    task = asyncio.create_task(rig.spotify.sign_in())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert rig.spotify.status.state is SpotifyState.SIGNING_IN
    await rig.spotify.sign_in()  # a second press while waiting does nothing
    assert len(rig.browser.listeners) == 1
    await rig.spotify.cancel_sign_in()
    await task
    assert rig.spotify.status.state is SpotifyState.SIGNED_OUT
    assert rig.spotify.status.error is None
    assert rig.browser.listeners[-1].closed


async def test_close_cancels_a_waiting_sign_in_and_the_http_session() -> None:
    rig = Rig({"client_id": CLIENT})
    await rig.spotify.load()
    rig.browser.answer = "never"
    task = asyncio.create_task(rig.spotify.sign_in())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await rig.spotify.close()
    await task
    assert rig.http.closed


async def test_code_exchange_refused_or_offline() -> None:
    rig = Rig({"client_id": CLIENT})
    await rig.spotify.load()
    rig.http.on("POST", TOKEN, HttpReply(400, {"error": "invalid_client"}))
    await rig.spotify.sign_in()
    assert rig.spotify.status.error is SpotifyErrorCode.SIGN_IN_FAILED
    assert rig.spotify.status.state is SpotifyState.SIGNED_OUT

    rig.http.fail = OSError("offline")
    await rig.spotify.sign_in()
    assert rig.spotify.status.error is SpotifyErrorCode.UNAVAILABLE


async def test_sign_out_keeps_or_forgets_the_client_id() -> None:
    rig = await signed_in()
    await rig.spotify.sign_out()
    assert rig.spotify.status.state is SpotifyState.SIGNED_OUT
    assert rig.file.data == {"client_id": CLIENT}
    assert rig.spotify.status.devices == ()
    await rig.spotify.sign_out(forget_client_id=True)
    assert rig.spotify.status.state is SpotifyState.NOT_SET_UP
    assert rig.file.data == {}


async def test_dashboard_opens_in_the_browser() -> None:
    rig = Rig()
    assert await rig.spotify.open_dashboard()
    assert rig.browser.opened == [DASHBOARD]


# Tokens


async def test_access_token_is_reused_then_refreshed_when_old() -> None:
    rig = await signed_in()
    await rig.spotify.refresh()
    assert len(rig.http.made("POST", TOKEN)) == 1
    rig.clock.now += 3600
    await rig.spotify.refresh()
    assert len(rig.http.made("POST", TOKEN)) == 2
    assert rig.http.made("GET", "/me/playlists")[-1]["token"] == "access-2"


async def test_refresh_token_that_spotify_no_longer_accepts() -> None:
    rig = Rig({"client_id": CLIENT, "refresh_token": "refresh-0"})
    rig.http.on("POST", TOKEN, HttpReply(400, {"error": "invalid_grant"}))
    await rig.spotify.load()
    status = rig.spotify.status
    assert status.state is SpotifyState.SIGNED_OUT
    assert status.error is SpotifyErrorCode.EXPIRED
    assert rig.file.data == {"client_id": CLIENT}


async def test_token_refused_for_another_reason_also_signs_out() -> None:
    rig = Rig({"client_id": CLIENT, "refresh_token": "refresh-0"})
    rig.http.on("POST", TOKEN, HttpReply(400, {"error": "invalid_client"}))
    await rig.spotify.load()
    assert rig.spotify.status.state is SpotifyState.SIGNED_OUT
    assert rig.spotify.status.error is SpotifyErrorCode.EXPIRED


async def test_token_service_down_keeps_the_sign_in() -> None:
    rig = Rig({"client_id": CLIENT, "refresh_token": "refresh-0"})
    rig.http.on("POST", TOKEN, HttpReply(503))
    await rig.spotify.load()
    assert rig.spotify.status.state is SpotifyState.SIGNED_IN
    assert rig.spotify.status.error is SpotifyErrorCode.UNAVAILABLE
    assert rig.file.data == {"client_id": CLIENT, "refresh_token": "refresh-0"}


async def test_a_401_gets_a_new_token_and_one_retry() -> None:
    rig = await signed_in()
    rig.http.on("GET", "/me/player/devices", HttpReply(401), HttpReply(200, DEVICES))
    await rig.spotify.refresh_devices()
    assert rig.spotify.status.error is None
    tokens = [c["token"] for c in rig.http.made("GET", "/me/player/devices")]
    assert tokens[-2:] == ["access-1", "access-2"]

    rig.http.on("GET", "/me/player/devices", HttpReply(401))
    await rig.spotify.refresh_devices()
    assert rig.spotify.status.error is SpotifyErrorCode.EXPIRED


# Lists, search and playback


async def test_search_maps_tracks_albums_and_playlists() -> None:
    rig = await signed_in()
    rig.http.on("GET", "/search", HttpReply(200, SEARCH))
    await rig.spotify.search("  invented   song ")
    call = rig.http.made("GET", "/search")[0]
    assert call["params"] == {
        "q": "invented song",
        "type": "track,album,playlist",
        "limit": str(SEARCH_LIMIT),
    }
    assert SEARCH_LIMIT == 10
    status = rig.spotify.status
    assert status.query == "invented song"
    assert not status.searching
    assert [(r.id, r.kind) for r in status.results] == [
        ("t:tr1", ItemKind.TRACK),
        ("a:al1", ItemKind.ALBUM),
        ("p:pl9", ItemKind.PLAYLIST),
    ]
    track, album, found = status.results
    assert track.subtitle == "Example Artist, Guest · Example Album"
    assert track.duration == 201.0
    assert track.has_art
    assert album.subtitle == "Example Artist · 2021"
    assert not album.has_art
    assert found.count == 4  # the old `tracks` field still works


async def test_search_clears_and_ignores_stale_answers() -> None:
    rig = await signed_in()
    gate = asyncio.Event()

    async def slow(*args: Any, **kwargs: Any) -> HttpReply:
        await gate.wait()
        return HttpReply(200, SEARCH)

    original = rig.http.request
    rig.http.request = slow  # type: ignore[method-assign]
    first = asyncio.create_task(rig.spotify.search("first"))
    await asyncio.sleep(0)
    rig.http.request = original  # type: ignore[method-assign]
    await rig.spotify.search("")
    gate.set()
    await first
    assert rig.spotify.status.query == ""
    assert rig.spotify.status.results == ()


async def test_search_errors_and_signed_out_search() -> None:
    rig = await signed_in()
    rig.http.on("GET", "/search", HttpReply(429))
    await rig.spotify.search("x")
    assert rig.spotify.status.error is SpotifyErrorCode.RATE_LIMITED
    await rig.spotify.sign_out()
    await rig.spotify.search("x")
    assert rig.spotify.status.query == ""


async def test_play_a_track_or_a_playlist_on_a_device() -> None:
    rig = await signed_in()
    rig.http.on("GET", "/search", HttpReply(200, SEARCH))
    await rig.spotify.search("song")
    assert await rig.spotify.play("t:tr1", "dev2")
    assert await rig.spotify.play("p:pl1")
    plays = rig.http.made("PUT", "/me/player/play")
    assert plays[0]["json"] == {"uris": ["spotify:track:tr1"]}
    assert plays[0]["params"] == {"device_id": "dev2"}
    assert plays[1]["json"] == {"context_uri": "spotify:playlist:pl1"}
    assert plays[1]["params"] is None
    assert not await rig.spotify.play("t:unknown")
    assert rig.spotify.status.error is SpotifyErrorCode.GONE


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        (HttpReply(404, {"error": {"status": 404, "reason": "NO_ACTIVE_DEVICE"}}), "no_device"),
        (HttpReply(404, {"error": {"status": 404, "reason": "OTHER"}}), "gone"),
        (
            HttpReply(403, {"error": {"status": 403, "reason": "PREMIUM_REQUIRED"}}),
            "premium_required",
        ),
        (HttpReply(403, {"error": {"status": 403}}), "not_allowed"),
        (HttpReply(429, None, retry_after=3), "rate_limited"),
        (HttpReply(502), "unavailable"),
    ],
)
async def test_player_errors(reply: HttpReply, error: str) -> None:
    rig = await signed_in()
    rig.http.on("PUT", "/me/player/play", reply)
    assert not await rig.spotify.play("p:pl1")
    assert rig.spotify.status.error is SpotifyErrorCode(error)
    await rig.spotify.dismiss_error()
    assert rig.spotify.status.error is None


async def test_offline() -> None:
    rig = await signed_in()
    rig.http.fail = OSError("offline")
    await rig.spotify.refresh()
    assert rig.spotify.status.error is SpotifyErrorCode.UNAVAILABLE
    assert not rig.spotify.status.loading


async def test_transfer_playback() -> None:
    rig = await signed_in()
    assert await rig.spotify.transfer("dev2")
    call = rig.http.made("PUT", "/me/player")[0]
    assert call["json"] == {"device_ids": ["dev2"], "play": True}
    assert not await rig.spotify.transfer("nope")
    assert rig.spotify.status.error is SpotifyErrorCode.GONE
    rig.http.on("PUT", "/me/player", HttpReply(403, {"error": {"reason": "PREMIUM_REQUIRED"}}))
    assert not await rig.spotify.transfer("dev1")
    assert rig.spotify.status.error is SpotifyErrorCode.PREMIUM_REQUIRED


async def test_nothing_happens_when_signed_out() -> None:
    rig = Rig({"client_id": CLIENT})
    await rig.spotify.load()
    await rig.spotify.refresh()
    await rig.spotify.refresh_devices()
    assert rig.http.calls == []


async def test_open_on_spotify_only_for_spotify_links() -> None:
    rig = await signed_in()
    assert await rig.spotify.open_item("p:pl1")
    assert rig.browser.opened == ["https://open.spotify.com/playlist/pl1"]
    rig.http.on(
        "GET",
        "/me/playlists",
        HttpReply(200, {"items": [playlist(2, external_urls={"spotify": "https://evil.test/x"})]}),
    )
    await rig.spotify.refresh()
    assert not await rig.spotify.open_item("p:pl2")
    assert not await rig.spotify.open_item("p:unknown")


async def test_artwork_is_fetched_once_and_kept_in_memory() -> None:
    rig = await signed_in()
    art = await rig.spotify.artwork("p:pl1")
    assert art is not None
    assert art.mimetype == "image/jpeg"
    assert await rig.spotify.artwork("p:pl1") is art
    assert rig.http.images == [ART]
    assert await rig.spotify.artwork("p:unknown") is None

    async def broken(url: str) -> SpotifyArt | None:
        raise OSError("offline")

    rig.http.image = broken  # type: ignore[method-assign]
    rig.http.on("GET", "/me/playlists", HttpReply(200, {"items": [playlist(3)]}))
    await rig.spotify.refresh()
    assert await rig.spotify.artwork("p:pl3") is None


async def test_nothing_private_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    rig = await signed_in()
    rig.http.on("GET", "/search", HttpReply(200, SEARCH))
    await rig.spotify.search("Invented Song")
    rig.http.on("PUT", "/me/player/play", HttpReply(500))
    await rig.spotify.play("t:tr1", "dev1")
    rig.http.on("POST", TOKEN, HttpReply(400, {"error": "invalid_grant"}))
    rig.clock.now += 7200
    await rig.spotify.refresh()
    text = caplog.text
    for private in ("Invented", "Example", "access-", "refresh-", CLIENT, "dev1", "pl1"):
        assert private not in text
