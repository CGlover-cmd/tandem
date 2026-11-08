"""The Music tab's library, radio and queue (Phase 6) on the demo's invented music."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiohttp
import pytest

from tandem.ui.controller import AppController
from tandem.ui.demo_backend import DemoBackend
from tandem.ui.demo_library import DEMO_FOLDER, DEMO_STATIONS
from tandem.ui.server import UiServer


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeFolderPicker:
    def __init__(self, folder: str | None) -> None:
        self.folder = folder
        self.asked = 0

    async def pick_folder(self) -> str | None:
        self.asked += 1
        return self.folder


async def _no_wait(_seconds: float) -> None:
    return None


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def picker() -> FakeFolderPicker:
    return FakeFolderPicker("C:\\Music\\Another Folder")


@pytest.fixture
async def controller(clock: Clock, picker: FakeFolderPicker) -> AsyncIterator[AppController]:
    demo = DemoBackend(sleep=_no_wait, clock=clock)
    controller = AppController(demo, demo_mode=True, clock=clock, folder_picker=picker)
    await controller.start()
    yield controller
    await controller.stop()


async def run(controller: AppController, command: dict[str, Any]) -> dict[str, Any]:
    controller.handle(command)
    await controller.runner.drain()
    return controller.snapshot()


async def test_the_library_arrives_without_songs(controller: AppController) -> None:
    library = controller.snapshot()["library"]
    assert library["folders"] == [DEMO_FOLDER]
    assert library["songCount"] == 11
    assert [a["title"] for a in library["albums"]] == ["Daybreak", "City Hours", "Quiet Rooms"]
    assert library["albums"][0] == {
        "id": "demo-album-1",
        "title": "Daybreak",
        "artist": "The Example Band",
        "year": 2021,
        "trackCount": 4,
        "hasArt": True,
    }
    assert library["openAlbum"] is None
    assert library["search"] == {"text": "", "songs": []}
    assert library["canPickFolders"] is True


async def test_open_an_album_and_search(controller: AppController) -> None:
    state = await run(controller, {"type": "openAlbum", "id": "demo-album-2"})
    album = state["library"]["openAlbum"]
    assert album["id"] == "demo-album-2"
    assert [s["title"] for s in album["songs"]] == ["Night Bus", "Rooftops", "Last Train"]
    assert album["songs"][0]["duration"] == 242.0
    state = await run(controller, {"type": "closeAlbum"})
    assert state["library"]["openAlbum"] is None

    state = await run(controller, {"type": "searchLibrary", "text": "example light"})
    assert [s["title"] for s in state["library"]["search"]["songs"]] == ["Morning Light"]
    state = await run(controller, {"type": "searchLibrary", "text": "   "})
    assert state["library"]["search"]["songs"] == []


async def test_play_an_album_and_drive_the_queue(controller: AppController, clock: Clock) -> None:
    state = await run(
        controller, {"type": "playAlbum", "id": "demo-album-1", "songId": "demo-album-1-2"}
    )
    player = state["player"]
    assert player["state"] == "playing"
    assert player["index"] == 1
    assert [q["title"] for q in player["queue"]] == [
        "Morning Light",
        "Paper Boats",
        "Window Seat",
        "Low Tide",
    ]
    assert player["queue"][0]["art"] == "demo-album-1"
    clock.now += 30
    assert controller.snapshot()["player"]["position"] == 30.0  # counts on while playing

    state = await run(controller, {"type": "player", "command": "play_pause"})
    assert state["player"]["state"] == "paused"
    clock.now += 30
    assert controller.snapshot()["player"]["position"] == 30.0
    state = await run(controller, {"type": "player", "command": "play_pause"})
    assert state["player"]["state"] == "playing"

    state = await run(controller, {"type": "queueSong", "id": "demo-album-2-1", "next": True})
    assert state["player"]["queue"][2]["title"] == "Night Bus"
    state = await run(controller, {"type": "queueAlbum", "id": "demo-album-3", "next": False})
    assert len(state["player"]["queue"]) == 9
    state = await run(controller, {"type": "player", "command": "next"})
    assert state["player"]["index"] == 2
    state = await run(controller, {"type": "player", "command": "previous"})
    assert state["player"]["index"] == 1
    last = state["player"]["queue"][-1]["id"]
    state = await run(controller, {"type": "removeQueueItem", "id": last})
    assert len(state["player"]["queue"]) == 8
    first = state["player"]["queue"][0]["id"]
    state = await run(controller, {"type": "playQueueItem", "id": first})
    assert state["player"]["index"] == 0
    state = await run(controller, {"type": "playSong", "id": "demo-album-3-2"})
    assert state["player"]["queue"][1]["title"] == "Slow Snow"
    assert state["player"]["index"] == 1
    state = await run(controller, {"type": "player", "command": "stop"})
    assert state["player"]["state"] == "stopped"
    state = await run(controller, {"type": "clearQueue"})
    assert state["player"]["queue"] == []


async def test_radio(controller: AppController) -> None:
    state = await run(controller, {"type": "searchRadio", "text": "jazz"})
    radio = state["radio"]
    assert [s["name"] for s in radio["results"]] == [DEMO_STATIONS[0].name]
    assert radio["results"][0] == {
        "id": "demo-station-1",
        "name": "Example FM Jazz",
        "codec": "MP3",
        "bitrate": 128,
        "country": "US",
        "tags": "jazz",
    }
    state = await run(controller, {"type": "saveStation", "id": "demo-station-1"})
    assert [s["id"] for s in state["radio"]["saved"]] == ["demo-station-2", "demo-station-1"]
    state = await run(controller, {"type": "playStation", "id": "demo-station-1"})
    assert state["player"]["queue"][0]["kind"] == "radio"
    assert state["player"]["state"] == "playing"
    state = await run(controller, {"type": "removeStation", "id": "demo-station-1"})
    assert [s["id"] for s in state["radio"]["saved"]] == ["demo-station-2"]
    state = await run(controller, {"type": "playStation", "id": "nope"})
    assert controller.message is not None


async def test_folders(controller: AppController, picker: FakeFolderPicker) -> None:
    state = await run(controller, {"type": "addMusicFolder"})
    assert picker.asked == 1
    assert state["library"]["folders"] == [DEMO_FOLDER, "C:\\Music\\Another Folder"]
    assert state["library"]["picking"] is False
    picker.folder = None  # cancelled
    state = await run(controller, {"type": "addMusicFolder"})
    assert len(state["library"]["folders"]) == 2
    state = await run(controller, {"type": "removeMusicFolder", "folder": DEMO_FOLDER})
    state = await run(
        controller, {"type": "removeMusicFolder", "folder": "C:\\Music\\Another Folder"}
    )
    assert state["library"]["albums"] == []
    state = await run(controller, {"type": "rescanLibrary"})
    assert state["library"]["songCount"] == 0


async def test_an_open_album_closes_when_its_folder_goes(controller: AppController) -> None:
    await run(controller, {"type": "openAlbum", "id": "demo-album-1"})
    await run(controller, {"type": "searchLibrary", "text": "light"})
    state = await run(controller, {"type": "removeMusicFolder", "folder": DEMO_FOLDER})
    assert state["library"]["openAlbum"] is None
    assert state["library"]["search"]["songs"] == []


@pytest.mark.parametrize(
    "command",
    [
        {"type": "player", "command": "shuffle"},
        {"type": "playAlbum"},
        {"type": "openAlbum", "id": 3},
        {"type": "searchLibrary", "text": 5},
        {"type": "removeMusicFolder"},
        {"type": "searchRadio"},
    ],
)
async def test_malformed_commands_are_ignored(
    controller: AppController, command: dict[str, Any]
) -> None:
    before = controller.snapshot()
    controller.handle(command)
    await controller.runner.drain()
    assert controller.snapshot() == before


async def test_album_art_needs_the_token(controller: AppController, tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>", "utf-8")
    server = UiServer(controller, static_dir=tmp_path)
    await server.start()
    try:
        async with aiohttp.ClientSession() as http:
            base = f"{server.origin}/library-art/demo-album-1"
            async with http.get(f"{base}?token={server.token}") as art:
                assert art.status == 200
                assert art.headers["Content-Type"] == "image/svg+xml"
                assert (await art.read()).startswith(b"<svg")
            async with http.get(f"{base}?token=wrong") as refused:
                assert refused.status == 403
            async with http.get(f"{server.origin}/library-art/nope?token={server.token}") as none:
                assert none.status == 404
    finally:
        await server.stop()


async def test_apple_music_catalog(controller: AppController, tmp_path: Path) -> None:
    state = await run(controller, {"type": "searchCatalog", "text": "harbour lights"})
    catalog = state["catalog"]
    assert [s["title"] for s in catalog["songs"]] == ["Harbour Lights", "Harbour Lights (Live)"]
    assert [a["title"] for a in catalog["albums"]] == ["Coastline"]
    assert catalog["songs"][0] == {
        "id": "demo-cat-s1",
        "title": "Harbour Lights",
        "artist": "Sample Singer",
        "album": "Coastline",
        "duration": 201.0,
        "hasArt": True,
    }
    await run(controller, {"type": "openInAppleMusic", "id": "demo-cat-s1"})
    await run(controller, {"type": "openInAppleMusic", "id": "nope"})
    assert controller.message is not None
    await run(controller, {"type": "searchCatalog", "text": 3})

    (tmp_path / "index.html").write_text("<!doctype html>", "utf-8")
    server = UiServer(controller, static_dir=tmp_path)
    await server.start()
    try:
        async with aiohttp.ClientSession() as http:
            art_url = f"{server.origin}/catalog-art/demo-cat-s1?token={server.token}"
            async with http.get(art_url) as art:
                assert art.status == 200
                assert art.headers["Content-Type"] == "image/svg+xml"
                assert "sandbox" in art.headers["Content-Security-Policy"]
            async with http.get(f"{server.origin}/catalog-art/demo-cat-s1") as refused:
                assert refused.status == 403
            async with http.get(f"{server.origin}/apple-music-badge?token={server.token}") as badge:
                assert badge.status == 404  # the demo has no badge: the page shows text
    finally:
        await server.stop()
