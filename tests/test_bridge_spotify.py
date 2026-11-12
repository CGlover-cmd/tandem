"""Spotify on the real engine (tandem.bridge_spotify), with the fakes from test_spotify.
Everything is invented (docs/PRIVACY.md)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiohttp
import pytest

from conftest import FakeBackend, ManualSleep
from tandem import bridge
from tandem.engine.adapters.spotify_web import listen
from tandem.engine.events import EventBus
from tandem.engine.service import Engine
from tandem.engine.settings import SettingsStore
from tandem.engine.spotify import HttpReply, Spotify
from tandem.ui import backend as ui
from test_spotify import CLIENT, PORT, SEARCH, Browser, FakeFile, FakeHttp


class Harness:
    def __init__(self, tmp_path: Path, sleep: ManualSleep, with_spotify: bool = True) -> None:
        bus = EventBus()
        self.engine = Engine(FakeBackend([]), bus=bus, sleep=sleep, discovery_interval=60.0)
        self.http = FakeHttp()
        self.http.on("GET", "/search", HttpReply(200, SEARCH))
        self.file = FakeFile({"client_id": CLIENT, "refresh_token": "refresh-0"})
        self.browser = Browser()
        spotify = Spotify(bus, self.http, self.file, self.browser.open, self.browser.listen)
        self.backend = bridge.EngineBackend(
            self.engine,
            SettingsStore(tmp_path / "settings.json", bus),
            spotify=spotify if with_spotify else None,
        )
        self.events: list[ui.BackendEvent] = []
        self.backend.subscribe(self.events.append)


@pytest.fixture
async def h(tmp_path: Path, manual_sleep: ManualSleep) -> AsyncIterator[Harness]:
    harness = Harness(tmp_path, manual_sleep)
    await harness.backend.start()
    yield harness
    manual_sleep.release()
    await harness.backend.stop()


async def test_signed_in_spotify_reaches_the_window(h: Harness) -> None:
    spotify = h.backend.spotify()
    assert spotify.state == "signed_in"
    assert spotify.redirect_uri == "http://127.0.0.1/callback"
    assert [p.title for p in spotify.playlists] == ["Example Playlist 1"]
    assert spotify.playlists[0] == ui.SpotifyItemSnapshot(
        "p:pl1", "playlist", "Example Playlist 1", "Demo Owner", None, True, 11
    )
    assert [(d.id, d.kind, d.active, d.restricted) for d in spotify.devices] == [
        ("dev1", "computer", True, False),
        ("dev2", "smartphone", False, False),
        ("dev3", "tv", False, True),
    ]
    assert any(isinstance(e, ui.SpotifyChanged) for e in h.events)


async def test_commands_pass_through(h: Harness) -> None:
    await h.backend.spotify_search("song")
    assert [r.kind for r in h.backend.spotify().results] == ["track", "album", "playlist"]
    await h.backend.spotify_play("t:tr1", "dev2")
    assert h.http.made("PUT", "/me/player/play")[0]["params"] == {"device_id": "dev2"}
    await h.backend.spotify_transfer("dev2")
    assert h.http.made("PUT", "/me/player")
    await h.backend.spotify_refresh()
    await h.backend.open_in_spotify("p:pl1")
    await h.backend.open_spotify_dashboard()
    assert len(h.browser.opened) == 2
    art = await h.backend.spotify_art("p:pl1")
    assert art == ui.MusicArtwork(b"\xff\xd8\xff", "image/jpeg")
    assert await h.backend.spotify_art("nope") is None
    h.http.on("PUT", "/me/player/play", HttpReply(404, {"error": {"reason": "NO_ACTIVE_DEVICE"}}))
    await h.backend.spotify_play("p:pl1", None)
    assert h.backend.spotify().error == "no_device"
    await h.backend.spotify_dismiss_error()
    assert h.backend.spotify().error is None


async def test_setup_sign_in_and_out(h: Harness) -> None:
    await h.backend.spotify_sign_out(forget_client_id=True)
    assert h.backend.spotify().state == "not_set_up"
    await h.backend.set_spotify_client_id(CLIENT)
    assert h.backend.spotify().state == "signed_out"
    await h.backend.spotify_sign_in()
    assert h.backend.spotify().state == "signed_in"
    await h.backend.spotify_cancel_sign_in()


async def test_without_spotify_everything_is_quiet(
    tmp_path: Path, manual_sleep: ManualSleep
) -> None:
    harness = Harness(tmp_path, manual_sleep, with_spotify=False)
    b = harness.backend
    await b.start()
    try:
        assert b.spotify() == ui.SpotifySnapshot()
        await b.set_spotify_client_id(CLIENT)
        await b.spotify_sign_in()
        await b.spotify_cancel_sign_in()
        await b.spotify_sign_out(True)
        await b.open_spotify_dashboard()
        await b.spotify_refresh()
        await b.spotify_search("x")
        await b.spotify_play("p:x", None)
        await b.spotify_transfer("d")
        await b.open_in_spotify("p:x")
        await b.spotify_dismiss_error()
        assert await b.spotify_art("p:x") is None
        assert harness.http.calls == []
    finally:
        manual_sleep.release()
        await b.stop()


# The loopback listener (real sockets, on 127.0.0.1 only)


async def test_loopback_listener_catches_the_redirect() -> None:
    listener = await listen("/callback")
    try:
        assert listener.port not in (0, PORT)
        base = f"http://127.0.0.1:{listener.port}"
        async with aiohttp.ClientSession() as http:
            async with http.get(f"{base}/favicon.ico") as other:
                assert other.status == 404
            async with http.get(f"{base}/callback?code=c1&state=s1") as page:
                assert page.status == 200
                assert "close this tab" in await page.text()
                assert "default-src 'none'" in page.headers["Content-Security-Policy"]
            async with http.get(f"{base}/callback?code=late&state=s2") as again:
                assert again.status == 200
        assert await listener.wait() == {"code": "c1", "state": "s1"}
    finally:
        await listener.close()
