"""Spotify in the window (Settings → Connections and the Music tab), on the demo's invented
playlists and devices."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiohttp
import pytest

from tandem.ui.controller import AppController
from tandem.ui.demo_backend import DemoBackend
from tandem.ui.server import UiServer

CLIENT = "a" * 32  # an invented Client ID


async def _no_wait(_seconds: float) -> None:
    return None


@pytest.fixture
async def demo() -> DemoBackend:
    return DemoBackend(sleep=_no_wait)


@pytest.fixture
async def controller(demo: DemoBackend) -> AsyncIterator[AppController]:
    controller = AppController(demo, demo_mode=True)
    await controller.start()
    yield controller
    await controller.stop()


async def run(controller: AppController, command: dict[str, Any]) -> dict[str, Any]:
    controller.handle(command)
    await controller.runner.drain()
    return controller.snapshot()["spotify"]


async def sign_in(controller: AppController) -> dict[str, Any]:
    await run(controller, {"type": "setSpotifyClientId", "clientId": CLIENT})
    return await run(controller, {"type": "spotifySignIn"})


async def test_setup_walkthrough(controller: AppController, demo: DemoBackend) -> None:
    spotify = controller.snapshot()["spotify"]
    assert spotify["state"] == "not_set_up"
    assert spotify["redirectUri"] == "http://127.0.0.1/callback"
    assert spotify["target"] is None

    await run(controller, {"type": "openSpotifyDashboard"})
    assert demo.spotify_opened == ["dashboard"]

    spotify = await run(controller, {"type": "setSpotifyClientId", "clientId": "nope"})
    assert spotify["error"] == "invalid_client_id"
    spotify = await run(controller, {"type": "spotifyDismissError"})
    assert spotify["error"] is None

    spotify = await sign_in(controller)
    assert spotify["state"] == "signed_in"
    assert [p["title"] for p in spotify["playlists"]] == [
        "Sunday Morning",
        "Focus Beats",
        "Road Trip Mix",
    ]
    assert spotify["playlists"][0] == {
        "id": "p:demo1",
        "kind": "playlist",
        "title": "Sunday Morning",
        "subtitle": "Demo User",
        "duration": None,
        "hasArt": True,
        "count": 24,
    }
    assert spotify["devices"][0] == {
        "id": "demo-dev-1",
        "name": "Demo Laptop",
        "kind": "computer",
        "active": True,
        "restricted": False,
    }
    assert spotify["target"] == "demo-dev-1"  # the active device

    spotify = await run(controller, {"type": "spotifySignOut"})
    assert spotify["state"] == "signed_out"
    spotify = await run(controller, {"type": "spotifySignOut", "forget": True})
    assert spotify["state"] == "not_set_up"


async def test_cancel_sign_in() -> None:
    gate = asyncio.Event()

    async def wait(_seconds: float) -> None:
        await gate.wait()

    demo = DemoBackend(sleep=_no_wait)
    controller = AppController(demo, demo_mode=True)
    await controller.start()
    demo._sleep = wait  # pyright: ignore[reportPrivateUsage]  # only sign-in waits from here
    try:
        await run(controller, {"type": "setSpotifyClientId", "clientId": CLIENT})
        await demo.spotify_cancel_sign_in()  # nothing to cancel
        controller.handle({"type": "spotifySignIn"})
        await asyncio.sleep(0)
        assert controller.snapshot()["spotify"]["state"] == "signing_in"
        controller.handle({"type": "spotifyCancelSignIn"})
        await asyncio.sleep(0)
        gate.set()
        await controller.runner.drain()
        assert controller.snapshot()["spotify"]["state"] == "signed_out"
    finally:
        gate.set()
        await controller.stop()


async def test_play_on_the_chosen_device(controller: AppController, demo: DemoBackend) -> None:
    await sign_in(controller)
    await run(controller, {"type": "spotifyPlay", "id": "p:demo2"})
    assert demo.spotify_played == [("p:demo2", "demo-dev-1")]

    spotify = await run(controller, {"type": "spotifyChooseDevice", "id": "demo-dev-2"})
    assert spotify["target"] == "demo-dev-2"
    spotify = await run(controller, {"type": "spotifyChooseDevice", "id": "demo-dev-3"})
    assert spotify["target"] == "demo-dev-2"  # restricted: Spotify won't take commands for it
    await run(controller, {"type": "spotifyPlay", "id": "p:demo1"})
    assert demo.spotify_played[-1] == ("p:demo1", "demo-dev-2")
    active = [d["id"] for d in controller.snapshot()["spotify"]["devices"] if d["active"]]
    assert active == ["demo-dev-2"]

    spotify = await run(controller, {"type": "spotifyTransfer", "id": "demo-dev-1"})
    assert spotify["target"] == "demo-dev-1"
    assert [d["id"] for d in spotify["devices"] if d["active"]] == ["demo-dev-1"]
    await run(controller, {"type": "spotifyTransfer", "id": "demo-dev-3"})  # ignored
    assert controller.snapshot()["spotify"]["target"] == "demo-dev-1"

    spotify = await run(controller, {"type": "spotifyPlay", "id": "p:gone"})
    assert spotify["error"] == "gone"


async def test_search_and_open_on_spotify(controller: AppController, demo: DemoBackend) -> None:
    await sign_in(controller)
    spotify = await run(controller, {"type": "spotifySearch", "text": "lantern"})
    assert spotify["query"] == "lantern"
    assert [r["kind"] for r in spotify["results"]] == ["track", "track", "playlist"]
    await run(controller, {"type": "spotifyPlay", "id": "t:demo1"})
    assert demo.spotify_played[-1] == ("t:demo1", "demo-dev-1")
    await run(controller, {"type": "openInSpotify", "id": "t:demo1"})
    assert demo.spotify_opened == ["t:demo1"]
    await run(controller, {"type": "spotifyRefresh"})
    await run(controller, {"type": "spotifySearch", "text": 5})  # malformed: ignored


async def test_chosen_device_is_dropped_when_it_goes(
    controller: AppController, demo: DemoBackend
) -> None:
    await sign_in(controller)
    await run(controller, {"type": "spotifyChooseDevice", "id": "demo-dev-2"})
    await demo.spotify_sign_out(False)
    await controller.runner.drain()
    assert controller.spotify.chosen_device is None
    assert controller.snapshot()["spotify"]["target"] is None


async def test_no_device_to_play_on(controller: AppController) -> None:
    await sign_in(controller)
    controller.spotify.spotify = controller.spotify.spotify.__class__(state="signed_in")
    spotify = await run(controller, {"type": "spotifyPlay", "id": "p:demo1"})
    assert spotify["error"] == "no_device"


async def test_artwork_route_needs_the_token(controller: AppController, tmp_path: Path) -> None:
    await sign_in(controller)
    (tmp_path / "index.html").write_text("<!doctype html>", "utf-8")
    server = UiServer(controller, static_dir=tmp_path)
    await server.start()
    try:
        async with aiohttp.ClientSession() as http:
            url = f"{server.origin}/spotify-art/p:demo1"
            async with http.get(f"{url}?token={server.token}") as art:
                assert art.status == 200
                assert art.headers["Content-Type"] == "image/svg+xml"
                assert "sandbox" in art.headers["Content-Security-Policy"]
            async with http.get(url) as refused:
                assert refused.status == 403
            async with http.get(f"{server.origin}/spotify-art/x?token={server.token}") as none:
                assert none.status == 404
    finally:
        await server.stop()
