"""Send media to an Apple TV (Phase 7). Paths and links are invented (docs/PRIVACY.md)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiohttp
import pytest

from conftest import FakeBackend, ManualSleep, make_device
from tandem.engine.media_send import (
    MediaError,
    MediaSendChanged,
    MediaServer,
    SendState,
    is_link,
    local_address_towards,
    title_for,
)
from tandem.engine.models import DeviceKind, Service
from tandem.engine.service import Engine

TV = make_device(
    kind=DeviceKind.APPLE_TV,
    name="Living Room TV",
    address="127.0.0.1",
    services=frozenset({Service.AIRPLAY, Service.COMPANION}),
)


async def _wait(predicate: object, *, tries: int = 500) -> None:
    for _ in range(tries):
        if callable(predicate) and predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition not reached")


def test_links_and_titles() -> None:
    assert is_link(" https://media.example/clip.mp4 ")
    assert not is_link("C:/Videos/clip.mp4")
    assert title_for("https://media.example/films/clip.mp4") == "clip.mp4"
    assert title_for("https://media.example/") == "media.example"
    assert title_for("C:/Videos/holiday.mov") == "holiday.mov"
    assert local_address_towards("127.0.0.1") == "127.0.0.1"


async def test_server_shares_only_registered_files(tmp_path: Path) -> None:
    clip = tmp_path / "clip one.mp4"
    clip.write_bytes(b"0123456789")
    server = MediaServer(host="127.0.0.1")
    await server.start()
    await server.start()  # once
    assert server.running
    path = server.share(clip)
    async with aiohttp.ClientSession() as http:
        base = f"http://127.0.0.1:{server.port}"
        async with http.get(base + path) as response:
            assert response.status == 200
            assert await response.read() == b"0123456789"
        async with http.get(base + path, headers={"Range": "bytes=2-4"}) as response:
            assert response.status == 206
            assert await response.read() == b"234"
        async with http.get(base + "/media/guess/clip.mp4") as response:
            assert response.status == 404
    await server.stop()
    assert not server.running


async def test_play_a_link_then_a_file(tmp_path: Path, manual_sleep: ManualSleep) -> None:
    backend = FakeBackend([TV])
    engine = Engine(backend, sleep=manual_sleep)
    await engine.scan()
    events: list[tuple[SendState, str | None]] = []
    engine.bus.subscribe(MediaSendChanged, lambda e: events.append((e.state, e.title)))

    await engine.play_media(TV.id, "https://media.example/clip.mp4")
    sender = backend.senders[TV.id]
    await _wait(lambda: sender.urls)
    assert sender.urls == ["https://media.example/clip.mp4"]
    assert engine.sending_media(TV.id)

    video = tmp_path / "holiday.mov"
    video.write_bytes(b"x")
    await engine.play_media(TV.id, str(video))  # replaces the link
    await _wait(lambda: len(sender.urls) == 2)
    assert sender.urls[1].startswith("http://127.0.0.1:")
    assert sender.urls[1].endswith("/holiday.mov")
    sender.release.set()
    await _wait(lambda: events[-1][0] is SendState.ENDED)
    assert (SendState.PLAYING, "clip.mp4") in events
    assert not engine.sending_media(TV.id)
    await engine.stop_media(TV.id)
    await engine.close()


async def test_send_problems(tmp_path: Path, manual_sleep: ManualSleep) -> None:
    backend = FakeBackend([TV])
    engine = Engine(backend, sleep=manual_sleep)
    await engine.scan()
    with pytest.raises(MediaError, match="isn't there"):
        await engine.play_media(TV.id, str(tmp_path / "missing.mp4"))
    states: list[SendState] = []
    engine.bus.subscribe(MediaSendChanged, lambda e: states.append(e.state))
    backend.senders[TV.id].fail = OSError("TV refused")
    await engine.play_media(TV.id, "https://media.example/clip.mp4")
    await _wait(lambda: SendState.FAILED in states)
    backend.media_enabled = False
    with pytest.raises(MediaError, match="can't play"):
        await engine.play_media(TV.id, "https://media.example/clip.mp4")
    await engine.close()
