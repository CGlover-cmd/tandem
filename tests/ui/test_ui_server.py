from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiohttp
import pytest

from tandem.ui.controller import AppController
from tandem.ui.demo_backend import DemoBackend
from tandem.ui.server import UiServer

DEV_ORIGIN = "http://localhost:5173"


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Tandem</title>", "utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log('hi')", "utf-8")
    return tmp_path


@pytest.fixture
async def running(
    backend: DemoBackend, static_dir: Path
) -> AsyncIterator[tuple[AppController, UiServer]]:
    controller = AppController(backend, demo_mode=True)
    server = UiServer(controller, static_dir=static_dir, extra_origins=[DEV_ORIGIN])
    await server.start()
    await controller.start()
    yield controller, server
    await server.stop()
    await controller.stop()


async def _next_state(socket: aiohttp.ClientWebSocketResponse) -> dict[str, Any]:
    message = await asyncio.wait_for(socket.receive_str(), timeout=5)
    data = json.loads(message)
    assert data["type"] == "state"
    return data["state"]


def _ws_url(server: UiServer, token: str | None = None) -> str:
    return f"ws://127.0.0.1:{server.port}/ws?token={server.token if token is None else token}"


async def test_serves_the_page_and_assets(running: tuple[AppController, UiServer]) -> None:
    _, server = running
    assert server.port > 0
    assert server.url.startswith(f"http://127.0.0.1:{server.port}/?token=")
    async with aiohttp.ClientSession() as http:
        async with http.get(server.url) as page:
            assert page.status == 200
            assert "<title>Tandem</title>" in await page.text()
            assert page.headers["Cache-Control"] == "no-store"
        async with http.get(f"{server.origin}/assets/app.js") as script:
            assert script.status == 200


async def test_missing_build_explains_how_to_build(backend: DemoBackend, tmp_path: Path) -> None:
    server = UiServer(AppController(backend), static_dir=tmp_path / "nothing")
    await server.start()
    try:
        async with aiohttp.ClientSession() as http, http.get(server.origin) as page:
            assert "npm --prefix web run build" in await page.text()
    finally:
        await server.stop()


async def test_other_host_names_are_refused(running: tuple[AppController, UiServer]) -> None:
    _, server = running
    async with (
        aiohttp.ClientSession() as http,
        http.get(server.origin, headers={"Host": f"attacker.example:{server.port}"}) as page,
    ):
        assert page.status == 421


@pytest.mark.parametrize(
    ("token", "origin"),
    [
        ("wrong", None),
        ("", None),
        (None, "http://attacker.example"),
        (None, ""),
    ],
)
async def test_websocket_needs_the_token_and_a_known_origin(
    running: tuple[AppController, UiServer], token: str | None, origin: str | None
) -> None:
    _, server = running
    headers = {"Origin": server.origin if origin is None else origin}
    if origin == "":
        headers = {}
    async with aiohttp.ClientSession() as http:
        with pytest.raises(aiohttp.WSServerHandshakeError) as refused:
            await http.ws_connect(_ws_url(server, token), headers=headers)
    assert refused.value.status == 403


async def test_websocket_sends_state_and_runs_commands(
    running: tuple[AppController, UiServer],
) -> None:
    controller, server = running
    async with (
        aiohttp.ClientSession() as http,
        http.ws_connect(_ws_url(server), headers={"Origin": DEV_ORIGIN}) as socket,
    ):
        state = await _next_state(socket)
        assert len(state["devices"]) == 4

        await socket.send_str("not json")
        await socket.send_str("[1, 2]")
        await socket.send_json({"type": "connect", "id": "demo-speaker-1"})

        while True:
            state = await _next_state(socket)
            speaker = next(d for d in state["devices"] if d["id"] == "demo-speaker-1")
            if speaker["state"] == "connected":
                break
        assert controller.device("demo-speaker-1") is not None


async def test_stop_closes_open_sockets(backend: DemoBackend, static_dir: Path) -> None:
    controller = AppController(backend)
    server = UiServer(controller, static_dir=static_dir)
    await server.start()
    async with aiohttp.ClientSession() as http:
        socket = await http.ws_connect(_ws_url(server), headers={"Origin": server.origin})
        await _next_state(socket)

        await server.stop()

        message = await asyncio.wait_for(socket.receive(), timeout=5)
        assert message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED)
        await socket.close()
