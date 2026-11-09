"""The Music tab's library, radio, catalog and queue (Phase 6) on the demo: the real library,
radio, catalog and player over invented music (ADR-0019)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiohttp
import pytest
from demo_harness import demo_backend, settle, until

from tandem.bridge import DemoBackend
from tandem.engine.adapters.demo_music import DEMO_FOLDER
from tandem.ui.controller import AppController
from tandem.ui.server import UiServer


class FakeFolderPicker:
    def __init__(self, folder: str | None) -> None:
        self.folder = folder
        self.asked = 0

    async def pick_folder(self) -> str | None:
        self.asked += 1
        return self.folder


@pytest.fixture
def picker(tmp_path: Path) -> FakeFolderPicker:
    folder = tmp_path / "Another Folder"
    folder.mkdir()
    return FakeFolderPicker(str(folder))


@pytest.fixture
async def started(picker: FakeFolderPicker) -> AsyncIterator[tuple[AppController, DemoBackend]]:
    backend = demo_backend()
    controller = AppController(backend, demo_mode=True, folder_picker=picker)
    await controller.start()
    await until(lambda: controller.snapshot()["library"]["songCount"] == 11)
    yield controller, backend
    await controller.stop()


@pytest.fixture
def controller(started: tuple[AppController, DemoBackend]) -> AppController:
    return started[0]


async def run(controller: AppController, command: dict[str, Any]) -> dict[str, Any]:
    controller.handle(command)
    await settle(controller)
    return controller.snapshot()


def album(controller: AppController, title: str) -> str:
    albums = controller.snapshot()["library"]["albums"]
    return next(a["id"] for a in albums if a["title"] == title)


async def songs(controller: AppController, title: str) -> dict[str, str]:
    state = await run(controller, {"type": "openAlbum", "id": album(controller, title)})
    return {s["title"]: s["id"] for s in state["library"]["openAlbum"]["songs"]}


def _without_music(snapshot: dict[str, Any]) -> dict[str, Any]:
    """The snapshot less the PC's music, whose position counts on in real time."""
    return {key: value for key, value in snapshot.items() if key != "music"}


def player(controller: AppController) -> dict[str, Any]:
    return controller.snapshot()["player"]


async def test_the_library_arrives_without_songs(controller: AppController) -> None:
    library = controller.snapshot()["library"]
    assert library["folders"] == [DEMO_FOLDER]
    assert sorted(a["title"] for a in library["albums"]) == [
        "City Hours",
        "Daybreak",
        "Quiet Rooms",
    ]
    daybreak = next(a for a in library["albums"] if a["title"] == "Daybreak")
    assert daybreak == {
        "id": album(controller, "Daybreak"),
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
    city = album(controller, "City Hours")
    state = await run(controller, {"type": "openAlbum", "id": city})
    opened = state["library"]["openAlbum"]
    assert opened["id"] == city
    assert [s["title"] for s in opened["songs"]] == ["Night Bus", "Rooftops", "Last Train"]
    assert opened["songs"][0]["duration"] == 242.0
    state = await run(controller, {"type": "closeAlbum"})
    assert state["library"]["openAlbum"] is None

    state = await run(controller, {"type": "searchLibrary", "text": "example light"})
    assert [s["title"] for s in state["library"]["search"]["songs"]] == ["Morning Light"]
    state = await run(controller, {"type": "searchLibrary", "text": "   "})
    assert state["library"]["search"]["songs"] == []


async def test_play_an_album_and_drive_the_queue(controller: AppController) -> None:
    daybreak = await songs(controller, "Daybreak")
    await run(
        controller,
        {
            "type": "playAlbum",
            "id": album(controller, "Daybreak"),
            "songId": daybreak["Paper Boats"],
        },
    )
    await until(lambda: player(controller)["state"] == "playing")
    state = player(controller)
    assert state["index"] == 1
    assert [q["title"] for q in state["queue"]] == [
        "Morning Light",
        "Paper Boats",
        "Window Seat",
        "Low Tide",
    ]
    assert state["queue"][0]["art"] == album(controller, "Daybreak")
    assert state["duration"] == 187.0

    await run(controller, {"type": "player", "command": "play_pause"})
    await until(lambda: player(controller)["state"] == "paused")
    await run(controller, {"type": "player", "command": "play_pause"})
    await until(lambda: player(controller)["state"] == "playing")

    city = await songs(controller, "City Hours")
    await run(controller, {"type": "queueSong", "id": city["Night Bus"], "next": True})
    assert player(controller)["queue"][2]["title"] == "Night Bus"
    await run(controller, {"type": "queueAlbum", "id": album(controller, "Quiet Rooms")})
    assert len(player(controller)["queue"]) == 9
    await run(controller, {"type": "player", "command": "next"})
    await until(lambda: player(controller)["index"] == 2)
    await run(controller, {"type": "player", "command": "previous"})
    await until(lambda: player(controller)["index"] == 1)
    last = player(controller)["queue"][-1]["id"]
    await run(controller, {"type": "removeQueueItem", "id": last})
    assert len(player(controller)["queue"]) == 8
    first = player(controller)["queue"][0]["id"]
    await run(controller, {"type": "playQueueItem", "id": first})
    await until(lambda: player(controller)["index"] == 0)

    quiet = await songs(controller, "Quiet Rooms")
    await run(controller, {"type": "playSong", "id": quiet["Slow Snow"]})
    await until(lambda: player(controller)["index"] == 1)
    assert player(controller)["queue"][1]["title"] == "Slow Snow"
    await run(controller, {"type": "player", "command": "stop"})
    await until(lambda: player(controller)["state"] == "stopped")
    await run(controller, {"type": "clearQueue"})
    await until(lambda: player(controller)["queue"] == [])


async def test_playing_switches_the_audio_source_to_the_player(controller: AppController) -> None:
    await run(controller, {"type": "playAlbum", "id": album(controller, "City Hours")})
    assert controller.snapshot()["audio"]["source"] == "player"


async def test_radio(controller: AppController) -> None:
    state = await run(controller, {"type": "searchRadio", "text": "jazz"})
    radio = state["radio"]
    assert radio["results"] == [
        {
            "id": "demo-station-1",
            "name": "Example FM Jazz",
            "codec": "MP3",
            "bitrate": 128,
            "country": "US",
            "tags": "jazz",
        }
    ]
    state = await run(controller, {"type": "saveStation", "id": "demo-station-1"})
    assert [s["id"] for s in state["radio"]["saved"]] == ["demo-station-1"]
    await run(controller, {"type": "playStation", "id": "demo-station-1"})
    await until(lambda: player(controller)["state"] == "playing")
    assert player(controller)["queue"][0]["kind"] == "radio"
    assert player(controller)["duration"] is None
    state = await run(controller, {"type": "removeStation", "id": "demo-station-1"})
    assert state["radio"]["saved"] == []
    await run(controller, {"type": "playStation", "id": "nope"})
    assert controller.message is not None


async def test_folders(controller: AppController, picker: FakeFolderPicker) -> None:
    state = await run(controller, {"type": "addMusicFolder"})
    assert picker.asked == 1
    assert state["library"]["folders"] == [DEMO_FOLDER, picker.folder]
    assert state["library"]["picking"] is False
    picker.folder = None  # cancelled
    state = await run(controller, {"type": "addMusicFolder"})
    assert len(state["library"]["folders"]) == 2
    await run(controller, {"type": "removeMusicFolder", "folder": DEMO_FOLDER})
    state = await run(
        controller, {"type": "removeMusicFolder", "folder": state["library"]["folders"][1]}
    )
    assert state["library"]["albums"] == []
    state = await run(controller, {"type": "rescanLibrary"})
    assert state["library"]["songCount"] == 0


async def test_a_folder_that_isnt_there_is_refused(
    controller: AppController, picker: FakeFolderPicker, tmp_path: Path
) -> None:
    picker.folder = str(tmp_path / "missing")
    state = await run(controller, {"type": "addMusicFolder"})
    assert state["library"]["folders"] == [DEMO_FOLDER]
    assert controller.message is not None


async def test_an_open_album_closes_when_its_folder_goes(controller: AppController) -> None:
    await run(controller, {"type": "openAlbum", "id": album(controller, "Daybreak")})
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
        {"type": "searchCatalog", "text": 3},
    ],
)
async def test_malformed_commands_are_ignored(
    controller: AppController, command: dict[str, Any]
) -> None:
    before = _without_music(controller.snapshot())
    controller.handle(command)
    await settle(controller)
    assert _without_music(controller.snapshot()) == before


async def test_album_art_needs_the_token(controller: AppController, tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>", "utf-8")
    server = UiServer(controller, static_dir=tmp_path)
    await server.start()
    try:
        async with aiohttp.ClientSession() as http:
            base = f"{server.origin}/library-art/{album(controller, 'Daybreak')}"
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


async def test_apple_music_catalog(
    started: tuple[AppController, DemoBackend], tmp_path: Path
) -> None:
    controller, backend = started
    state = await run(controller, {"type": "searchCatalog", "text": "harbour lights"})
    catalog = state["catalog"]
    assert [s["title"] for s in catalog["songs"]] == ["Harbour Lights", "Harbour Lights (Live)"]
    assert [a["title"] for a in catalog["albums"]] == ["Coastline", "Coastline Live"]
    assert catalog["songs"][0] == {
        "id": "s1000000011",
        "title": "Harbour Lights",
        "artist": "Sample Singer",
        "album": "Coastline",
        "duration": 201.0,
        "hasArt": True,
    }
    await run(controller, {"type": "openInAppleMusic", "id": "s1000000011"})
    assert backend.demo.music.opened == [
        "music://music.apple.com/us/album/demo/1000000001?i=1000000011"
    ]
    assert controller.message is None
    await run(controller, {"type": "openInAppleMusic", "id": "nope"})
    assert controller.message is not None

    (tmp_path / "index.html").write_text("<!doctype html>", "utf-8")
    server = UiServer(controller, static_dir=tmp_path)
    await server.start()
    try:
        async with aiohttp.ClientSession() as http:
            art_url = f"{server.origin}/catalog-art/s1000000011?token={server.token}"
            async with http.get(art_url) as art:
                assert art.status == 200
                assert art.headers["Content-Type"] == "image/svg+xml"
                assert "sandbox" in art.headers["Content-Security-Policy"]
            async with http.get(f"{server.origin}/catalog-art/s1000000011") as refused:
                assert refused.status == 403
            async with http.get(f"{server.origin}/apple-music-badge?token={server.token}") as badge:
                assert badge.status == 404  # the demo has no badge: the page shows text
    finally:
        await server.stop()
