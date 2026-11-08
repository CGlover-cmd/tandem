"""The Music tab's state, commands and artwork (Phase 6), on the demo backend's invented music."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiohttp
import pytest

from tandem.ui.backend import ControlError, MusicCommand
from tandem.ui.controller import AppController
from tandem.ui.demo_backend import DEMO_TRACKS, DemoBackend
from tandem.ui.server import UiServer


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def _no_wait(_seconds: float) -> None:
    return None


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def demo(clock: FakeClock) -> DemoBackend:
    return DemoBackend(sleep=_no_wait, clock=clock)


@pytest.fixture
async def controller(demo: DemoBackend, clock: FakeClock) -> AsyncIterator[AppController]:
    controller = AppController(demo, demo_mode=True, clock=clock)
    await controller.start()
    yield controller
    await controller.stop()


async def test_snapshot_counts_on_while_playing(
    controller: AppController, clock: FakeClock
) -> None:
    music = controller.snapshot()["music"]
    assert music == {
        "app": "Demo Player",
        "state": "playing",
        "title": "Morning Light",
        "artist": "The Example Band",
        "album": "Daybreak",
        "position": 42.0,
        "duration": 214.0,
        "commands": ["next", "play_pause", "previous"],
        "canSeek": True,
        "artwork": 1,
    }
    clock.now += 10
    assert controller.snapshot()["music"]["position"] == 52.0
    clock.now += 1000
    assert controller.snapshot()["music"]["position"] == 214.0  # never past the end


async def test_commands_from_the_page(controller: AppController, clock: FakeClock) -> None:
    controller.handle({"type": "music", "command": "play_pause"})
    await controller.runner.drain()
    assert controller.music is not None
    assert controller.music.state == "paused"
    clock.now += 10
    assert controller.snapshot()["music"]["position"] == 42.0  # paused: no counting

    controller.handle({"type": "music", "command": "next"})
    await controller.runner.drain()
    music = controller.snapshot()["music"]
    assert (music["title"], music["position"], music["artwork"]) == (DEMO_TRACKS[1][0], 0.0, 2)

    controller.handle({"type": "music", "command": "previous"})
    controller.handle({"type": "music", "command": "previous"})
    await controller.runner.drain()
    assert controller.snapshot()["music"]["title"] == DEMO_TRACKS[-1][0]  # wraps round

    controller.handle({"type": "musicSeek", "position": 30})
    await controller.runner.drain()
    assert controller.snapshot()["music"]["position"] == 30.0


@pytest.mark.parametrize(
    "command",
    [
        {"type": "music", "command": "shuffle"},
        {"type": "music"},
        {"type": "musicSeek", "position": -1},
        {"type": "musicSeek", "position": True},
        {"type": "musicSeek", "position": "10"},
    ],
)
async def test_malformed_music_commands_are_ignored(
    controller: AppController, command: dict[str, object]
) -> None:
    before = controller.snapshot()["music"]
    controller.handle(command)
    await controller.runner.drain()
    assert controller.snapshot()["music"] == before
    assert controller.message is None


async def test_nothing_playing(controller: AppController, demo: DemoBackend) -> None:
    demo.stop_music()
    assert controller.snapshot()["music"] is None
    assert controller.music_artwork() is None

    controller.music_command(MusicCommand.NEXT)
    await controller.runner.drain()
    assert controller.message == {"code": "nothingPlaying"}
    with pytest.raises(ControlError):
        await demo.music_seek(1.0)
    assert demo.music_artwork() is None


async def test_artwork_is_served_with_the_token_only(
    controller: AppController, demo: DemoBackend, tmp_path: Path
) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>", "utf-8")
    server = UiServer(controller, static_dir=tmp_path)
    await server.start()
    try:
        async with aiohttp.ClientSession() as http:
            url = f"{server.origin}/artwork?token={server.token}&v=1"
            async with http.get(url) as art:
                assert art.status == 200
                assert art.headers["Content-Type"] == "image/svg+xml"
                assert art.headers["Cache-Control"] == "no-store"
                assert (await art.read()).startswith(b"<svg")
            async with http.get(f"{server.origin}/artwork?token=wrong") as refused:
                assert refused.status == 403
            async with http.get(f"{server.origin}/artwork") as refused:
                assert refused.status == 403
            demo.stop_music()
            async with http.get(url) as gone:
                assert gone.status == 404
    finally:
        await server.stop()
