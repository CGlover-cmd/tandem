"""Cast the screen to an Apple TV (ADR-0006 addendum). Devices are invented (docs/PRIVACY.md)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import aiohttp
import pytest

from conftest import FakeBackend, FakeScreenEncoder, FakeSender, make_device
from tandem.engine.adapters import screen_capture
from tandem.engine.events import Event
from tandem.engine.media_send import MediaSendChanged, MediaServer, SendState, is_local_peer
from tandem.engine.models import DeviceKind, Service
from tandem.engine.screen_cast import (
    PLAYLIST,
    CastError,
    CastFolder,
    CastQuality,
    CastState,
    Screen,
    ScreenCastChanged,
    ScreenCasts,
    is_cast_file,
    segments_listed,
    settings_for,
)
from tandem.engine.service import AudioSource, Engine

TV = make_device(
    id="AA:BB:CC:00:00:41",
    kind=DeviceKind.APPLE_TV,
    name="Living Room TV",
    address="127.0.0.1",
    services=frozenset({Service.AIRPLAY, Service.COMPANION}),
)
DEN_TV = make_device(
    id="AA:BB:CC:00:00:42",
    kind=DeviceKind.APPLE_TV,
    name="Den TV",
    address="127.0.0.1",
    services=frozenset({Service.AIRPLAY, Service.COMPANION}),
)


async def _until(check: Callable[[], bool], timeout: float = 3.0) -> None:
    """Wait in real time: the encoder and folder work run on worker threads."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not check():
        if loop.time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.01)


def test_presets_and_file_names() -> None:
    standard = settings_for(CastQuality.STANDARD)
    assert (standard.width, standard.height, standard.fps) == (1920, 1080, 30)
    low = settings_for(CastQuality.LOW, 3, sound=False)
    assert (low.screen, low.width, low.sound) == (3, 1280, False)
    assert settings_for(CastQuality.HIGH).bitrate > standard.bitrate > low.bitrate
    assert is_cast_file(PLAYLIST)
    assert is_cast_file("index12.ts")
    for name in ("index.ts", "../index1.ts", "index1.ts.bak", "other.m3u8", "notes.txt"):
        assert not is_cast_file(name)
    assert segments_listed("#EXTM3U\n#EXTINF:1.0,\nindex0.ts\n#EXTINF:1.0,\nindex1.ts\n") == 2


def test_only_the_home_network_is_served() -> None:
    # Invented addresses (docs/PRIVACY.md): the documentation range counts as private here.
    for local in ("127.0.0.1", "192.0.2.20", "198.51.100.7"):
        assert is_local_peer(local)
    assert is_local_peer("fe80::1%12")  # link-local IPv6, with its interface
    assert is_local_peer("::ffff:192.0.2.20")  # IPv4 through an IPv6 socket
    assert is_local_peer("fd00::5")
    for outside in ("8.8.8.8", "2001:4860:4860::8888", "", None, "not an address"):
        assert not is_local_peer(outside)


def test_cast_folder_is_temporary(tmp_path: Path) -> None:
    folder = CastFolder(tmp_path)
    assert folder.path.parent == tmp_path
    assert folder.playlist() is None
    (folder.path / PLAYLIST).write_text("#EXTM3U\n", encoding="utf-8")
    assert folder.playlist() == "#EXTM3U\n"
    folder.remove()
    assert not folder.path.exists()


async def test_server_shares_only_cast_files_and_never_caches(tmp_path: Path) -> None:
    (tmp_path / PLAYLIST).write_bytes(b"#EXTM3U\n")
    (tmp_path / "index0.ts").write_bytes(b"segment")
    (tmp_path / "secret.txt").write_text("not shared", encoding="utf-8")
    server = MediaServer(host="127.0.0.1")
    await server.start()
    path = server.share_folder(tmp_path, is_cast_file, PLAYLIST)
    assert path.endswith("/" + PLAYLIST)
    folder_url = f"http://127.0.0.1:{server.port}{path.rsplit('/', 1)[0]}/"
    async with aiohttp.ClientSession() as http:
        async with http.get(folder_url + PLAYLIST) as response:
            assert response.status == 200
            assert response.content_type == "application/vnd.apple.mpegurl"
            assert response.headers["Cache-Control"] == "no-cache"
            assert await response.text() == "#EXTM3U\n"
        async with http.get(folder_url + "index0.ts") as response:
            assert response.content_type == "video/mp2t"
            assert await response.read() == b"segment"
        for name in ("secret.txt", "index9.ts"):  # not a cast file; not written (yet)
            async with http.get(folder_url + name) as response:
                assert response.status == 404
        server.unshare(path)
        async with http.get(folder_url + PLAYLIST) as response:
            assert response.status == 404
    server.unshare("/somewhere/else")  # not one of ours: ignored
    await server.stop()


async def _engine(backend: FakeBackend | None = None) -> tuple[Engine, FakeBackend, list[Event]]:
    backend = backend or FakeBackend([TV, DEN_TV])
    engine = Engine(backend)
    await engine.open()
    await engine.scan()
    events: list[Event] = []
    engine.bus.subscribe(ScreenCastChanged, events.append)
    return engine, backend, events


def _states(events: list[Event], device_id: str = TV.id) -> list[CastState]:
    return [
        e.state for e in events if isinstance(e, ScreenCastChanged) and e.device_id == device_id
    ]


async def test_cast_plays_the_live_playlist_and_stops() -> None:
    engine, backend, events = await _engine()
    assert [s.index for s in engine.screens()] == [0, 1]
    await engine.cast_screen(TV.id, quality=CastQuality.LOW, screen=1)
    assert engine.casting() == TV.id
    sender = backend.senders[TV.id]
    await _until(lambda: bool(sender.urls))
    assert sender.urls[0].startswith("http://127.0.0.1:")
    assert sender.urls[0].endswith("/" + PLAYLIST)
    encoder = backend.encoders[0]
    folder, settings, sound = encoder.started[0]
    assert (settings.screen, settings.width) == (1, 1280)
    assert sound is not None  # the PC's sound goes with the picture
    segment = sender.urls[0].replace(PLAYLIST, "index1.ts")  # the TV can fetch the segments
    async with aiohttp.ClientSession() as http, http.get(segment) as response:
        assert await response.read() == bytes([1]) * 8

    await engine.stop_cast(DEN_TV.id)  # not that TV: nothing happens
    assert engine.casting() == TV.id
    await engine.stop_cast()
    assert engine.casting() is None
    assert _states(events) == [CastState.STARTING, CastState.PLAYING, CastState.ENDED]
    assert encoder.stops >= 1
    assert not folder.exists()
    await engine.close()


async def test_casting_mutes_the_pc_like_speakers_do() -> None:
    engine, backend, _events = await _engine()
    speakers = backend.speakers
    assert speakers is not None
    await engine.cast_screen(TV.id)
    await _until(lambda: speakers.outputs["endpoint-speakers"])
    await engine.stop_cast()
    await _until(lambda: not speakers.outputs["endpoint-speakers"])
    await engine.close()


async def test_an_unknown_screen_falls_back_to_the_main_one_and_the_player_is_silent() -> None:
    engine, backend, _events = await _engine()
    await engine.set_audio_source(AudioSource.PLAYER)
    await engine.cast_screen(TV.id, screen=7)
    _folder, settings, sound = backend.encoders[0].started[0]
    assert settings.screen == 0
    assert sound is None  # Tandem's player feeds the speakers only
    await engine.close()
    assert engine.casting() is None


async def test_what_cannot_cast_says_why() -> None:
    engine, backend, events = await _engine()
    backend.media_enabled = False
    with pytest.raises(CastError) as caught:
        await engine.cast_screen(TV.id)
    assert caught.value.reason == CastError.NOT_A_TV
    backend.media_enabled = True
    backend.cast_enabled = False
    with pytest.raises(CastError) as caught:
        await engine.cast_screen(TV.id)
    assert caught.value.reason == CastError.NO_SCREEN
    backend.cast_enabled = True
    backend.screen_list = []
    with pytest.raises(CastError) as caught:
        await engine.cast_screen(TV.id)
    assert caught.value.reason == CastError.NO_SCREEN
    backend.screen_list = [Screen(0, 1920, 1080, primary=True)]
    backend.encoder_options = {"fail_start": CastError(CastError.NO_SCREEN)}
    with pytest.raises(CastError):
        await engine.cast_screen(TV.id)
    failed = [e for e in events if isinstance(e, ScreenCastChanged)][-1]
    assert (failed.state, failed.reason) == (CastState.FAILED, CastError.NO_SCREEN)
    assert backend.encoders[-1].stops == 1
    assert engine.casting() is None
    await engine.close()


async def test_a_cast_and_a_send_to_the_same_tv_replace_each_other() -> None:
    engine, _backend, events = await _engine()
    sends: list[SendState] = []
    engine.bus.subscribe(MediaSendChanged, lambda e: sends.append(e.state))
    await engine.play_media(TV.id, "https://media.example/clip.mp4")
    await _until(lambda: SendState.PLAYING in sends)
    await engine.cast_screen(TV.id)
    await _until(lambda: SendState.ENDED in sends)
    assert not engine.sending_media(TV.id)
    await engine.play_media(TV.id, "https://media.example/clip.mp4")
    await _until(lambda: CastState.ENDED in _states(events))
    assert engine.casting() is None
    await engine.close()


async def test_one_cast_at_a_time() -> None:
    engine, _backend, events = await _engine()
    await engine.cast_screen(TV.id)
    await engine.cast_screen(DEN_TV.id)
    assert engine.casting() == DEN_TV.id
    assert _states(events, TV.id)[-1] is CastState.ENDED
    await engine.close()
    assert _states(events, DEN_TV.id)[-1] is CastState.ENDED


async def _casts(
    encoder: FakeScreenEncoder, sender: FakeSender, tmp_path: Path, **kwargs: float
) -> tuple[ScreenCasts, MediaServer, list[Event]]:
    events: list[Event] = []
    casts = ScreenCasts(events.append, poll=0.01, folder_parent=tmp_path, **kwargs)
    server = MediaServer(host="127.0.0.1")
    await server.start()
    await casts.start(TV.id, sender, encoder, settings_for(CastQuality.STANDARD), server, "")
    return casts, server, events


async def test_an_encoder_that_never_gets_ready_fails(tmp_path: Path) -> None:
    encoder = FakeScreenEncoder(segments=0)
    with pytest.raises(CastError) as caught:
        await _casts(encoder, FakeSender(), tmp_path, ready_timeout=0.05)
    assert caught.value.reason == CastError.ENCODER
    assert encoder.stops == 1
    assert not any(tmp_path.iterdir())  # noqa: ASYNC240  # the folder is gone


async def test_an_encoder_that_stops_by_itself_ends_the_cast(tmp_path: Path) -> None:
    encoder = FakeScreenEncoder()
    casts, server, events = await _casts(encoder, FakeSender(), tmp_path)
    encoder.failed = True
    await _until(lambda: casts.device_id is None)
    last = events[-1]
    assert isinstance(last, ScreenCastChanged)
    assert (last.state, last.reason) == (CastState.FAILED, CastError.ENCODER)
    assert not any(tmp_path.iterdir())  # noqa: ASYNC240
    await server.stop()


async def test_the_tv_refusing_or_finishing_ends_the_cast(tmp_path: Path) -> None:
    refusing = FakeSender()
    refusing.fail = ConnectionResetError("refused")
    casts, server, events = await _casts(FakeScreenEncoder(), refusing, tmp_path)
    await _until(lambda: casts.device_id is None)
    last = events[-1]
    assert isinstance(last, ScreenCastChanged)
    assert (last.state, last.reason) == (CastState.FAILED, "ConnectionResetError")
    await server.stop()

    finishing = FakeSender()
    finishing.release.set()  # the TV stopped playing (the user pressed Back)
    casts, server, events = await _casts(FakeScreenEncoder(), finishing, tmp_path)
    await _until(lambda: casts.device_id is None)
    last = events[-1]
    assert isinstance(last, ScreenCastChanged)
    assert (last.state, last.reason) == (CastState.ENDED, None)
    await casts.close()
    await server.stop()


def test_cast_sound_is_paced_and_padded_with_silence() -> None:
    class Capture:
        def __init__(self) -> None:
            self.callback: Callable[[bytes], None] | None = None
            self.stopped = False

        def start(self, on_pcm: Callable[[bytes], None]) -> None:
            self.callback = on_pcm

        def stop(self) -> None:
            self.stopped = True

    capture = Capture()
    sound = screen_capture._Sound(capture)  # pyright: ignore[reportPrivateUsage]
    sound.start()
    assert capture.callback is not None
    assert sound.take(2) == bytes(8)  # nothing captured: silence
    capture.callback(b"\x01" * 12)  # three frames
    assert sound.take(2) == b"\x01" * 8  # a chunk split across takes
    assert sound.take(2) == b"\x01" * 4 + bytes(4)
    for _ in range(100):  # far more than 200 ms: the oldest is dropped
        capture.callback(b"\x02" * 4_000)
    capture.callback(b"\x03" * 4)
    held = sound.take(screen_capture.SAMPLE_RATE)
    assert held.rstrip(b"\x00").endswith(b"\x03" * 4)
    assert len(held.rstrip(b"\x00")) <= screen_capture._SOUND_HELD  # pyright: ignore[reportPrivateUsage]
    sound.stop()
    assert capture.stopped
    assert isinstance(screen_capture.available(), bool)
