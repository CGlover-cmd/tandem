"""A speaker's own buttons control Tandem (DACP; ADR-0023)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import aiohttp
import pytest
from pyatv.support import rtsp

from conftest import FakeBackend, make_device
from tandem.engine.adapters import pyatv_dacp
from tandem.engine.pc_media import PcMediaCommand, PcNowPlaying
from tandem.engine.service import AudioSource, Engine
from tandem.engine.speaker_buttons import (
    SERVICE_TYPE,
    ButtonCommand,
    ButtonPress,
    Identity,
    SpeakerButtons,
    parse,
)

SPEAKER = make_device(id="AA:BB:CC:00:00:41", name="Hall Speaker", address="192.0.2.41")
IDENTITY = Identity("0123456789ABCDEF", "1234567")
SONG = PcNowPlaying(
    "playing", "Example Song", "Example Artist", "Example Album", "Spotify", True, True, True
)


# --- What a request asks for ---------------------------------------------------------------


def test_commands_are_read() -> None:
    assert parse("play", {}) == ButtonPress(ButtonCommand.PLAY)
    assert parse(" PlayPause ", {}) == ButtonPress(ButtonCommand.PLAY_PAUSE)
    assert parse("playresume", {}) == ButtonPress(ButtonCommand.PLAY)
    assert parse("nextitem", {}) == ButtonPress(ButtonCommand.NEXT)
    assert parse("volumeup", {}) == ButtonPress(ButtonCommand.VOLUME_UP)
    for ignored in ("mutetoggle", "beginff", "shuffle_songs", "volume"):
        assert parse(ignored, {}) is None, ignored


def test_reported_volumes_become_0_to_100() -> None:
    def level(query: dict[str, str]) -> float | None:
        press = parse("setproperty", query)
        return None if press is None else press.level

    assert level({"dmcp.volume": "40"}) == 40
    assert level({"dmcp.volume": "140"}) == 100
    assert level({"dmcp.device-volume": "0"}) == 100
    assert level({"dmcp.device-volume": "-15"}) == pytest.approx(50)
    assert level({"dmcp.device-volume": "-144"}) == 0
    assert level({"dmcp.volume": "loud"}) is None
    assert level({"dmcp.volume": "nan"}) is None
    assert level({"other": "1"}) is None


def test_identity_is_what_receivers_look_for() -> None:
    identity = Identity.new()
    assert len(identity.dacp_id) == 16
    int(identity.dacp_id, 16)
    assert identity.active_remote.isdigit()
    assert IDENTITY.service_name == "iTunes_Ctrl_0123456789ABCDEF"


# --- The button server ----------------------------------------------------------------------


class FakeAdvertiser:
    def __init__(self, fail: bool = False) -> None:
        self.published: list[tuple[Identity, int]] = []
        self.closed = 0
        self.fail = fail

    async def publish(self, identity: Identity, port: int) -> None:
        if self.fail:
            raise OSError("no multicast")
        self.published.append((identity, port))

    async def close(self) -> None:
        self.closed += 1
        if self.fail:
            raise OSError("no multicast")


async def test_the_server_takes_presses_with_the_token_only() -> None:
    advertiser = FakeAdvertiser()
    buttons = SpeakerButtons(advertiser, identity=IDENTITY, host="127.0.0.1")
    presses: list[tuple[str, ButtonPress]] = []

    async def handler(address: str, press: ButtonPress) -> None:
        presses.append((address, press))
        if press.command is ButtonCommand.STOP:
            raise RuntimeError("the handler failed")  # logged; the speaker still gets 204

    await buttons.start(handler)
    await buttons.start(handler)  # once only
    assert buttons.running
    assert advertiser.published == [(IDENTITY, buttons.port)]
    base = f"http://127.0.0.1:{buttons.port}/ctrl-int/1"
    async with aiohttp.ClientSession() as http:
        async with http.get(f"{base}/pause") as refused:
            assert refused.status == 403
        token = {"Active-Remote": IDENTITY.active_remote}
        for path in ("pause", "stop", "shuffle_songs", "setproperty?dmcp.volume=30"):
            async with http.get(f"{base}/{path}", headers=token) as answer:
                assert answer.status == 204, path
    await buttons.stop()
    assert not buttons.running
    assert advertiser.closed == 1
    assert [p.command for _, p in presses] == [
        ButtonCommand.PAUSE,
        ButtonCommand.STOP,
        ButtonCommand.VOLUME,
    ]
    assert presses[0][0] == "127.0.0.1"
    assert buttons.presses == 3


async def test_a_failed_announcement_leaves_the_server_up() -> None:
    buttons = SpeakerButtons(FakeAdvertiser(fail=True), host="127.0.0.1")

    async def handler(_address: str, _press: ButtonPress) -> None:
        pass

    await buttons.start(handler)
    assert buttons.running
    await buttons.stop()
    await buttons.stop()  # twice is harmless


# --- pyatv: the same identity on every stream, announced -----------------------------------


@pytest.fixture
def hook() -> Iterator[None]:
    yield
    rtsp.RtspSession.__init__ = pyatv_dacp._original_init  # type: ignore[method-assign]
    pyatv_dacp._identity = None  # pyright: ignore[reportPrivateUsage]


def test_rtsp_sessions_get_tandems_identity(hook: None) -> None:
    pyatv_dacp.install_hook(IDENTITY)
    pyatv_dacp.install_hook(IDENTITY)  # twice is harmless
    session = rtsp.RtspSession(MagicMock())
    assert session.dacp_id == IDENTITY.dacp_id
    assert session.active_remote == int(IDENTITY.active_remote)
    pyatv_dacp._identity = None  # pyright: ignore[reportPrivateUsage]
    plain = rtsp.RtspSession(MagicMock())
    assert plain.dacp_id != IDENTITY.dacp_id  # pyatv's own random pair


async def test_the_advertiser_announces_the_button_server(
    hook: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    infos: list[Any] = []

    class FakeZeroconf:
        async def async_register_service(self, info: Any) -> None:
            calls.append("register")
            infos.append(info)

        async def async_unregister_service(self, info: Any) -> None:
            calls.append("unregister")

        async def async_close(self) -> None:
            calls.append("close")

    import zeroconf.asyncio

    monkeypatch.setattr(zeroconf.asyncio, "AsyncZeroconf", FakeZeroconf)
    monkeypatch.setattr(pyatv_dacp, "read_addresses", lambda: frozenset({"192.0.2.5"}))
    advertiser = pyatv_dacp.ZeroconfAdvertiser()
    await advertiser.close()  # nothing published yet
    await advertiser.publish(IDENTITY, 3689)
    (info,) = infos
    assert info.type == SERVICE_TYPE
    assert info.name == f"{IDENTITY.service_name}.{SERVICE_TYPE}"
    assert info.port == 3689
    assert rtsp.RtspSession(MagicMock()).dacp_id == IDENTITY.dacp_id  # the hook is on
    await advertiser.close()
    assert calls == ["register", "unregister", "close"]


# --- What the engine does with a press --------------------------------------------------------


async def _engine() -> tuple[Engine, FakeBackend]:
    backend = FakeBackend([SPEAKER])
    engine = Engine(backend)
    await engine.scan()
    return engine, backend


async def test_play_and_pause_go_to_the_app_that_is_playing() -> None:
    engine, backend = await _engine()
    backend.sessions.now = SONG
    await engine.pc_media.refresh()
    await engine.speaker_button(SPEAKER.address, ButtonPress(ButtonCommand.PLAY))
    assert backend.sessions.commands == []  # already playing
    await engine.speaker_button(SPEAKER.address, ButtonPress(ButtonCommand.PAUSE))
    await engine.speaker_button(SPEAKER.address, ButtonPress(ButtonCommand.NEXT))
    assert backend.sessions.commands == [PcMediaCommand.PLAY_PAUSE, PcMediaCommand.NEXT]
    await engine.close()


async def test_buttons_go_to_tandems_player_when_it_is_the_source() -> None:
    engine, _backend = await _engine()
    engine.audio_source = AudioSource.PLAYER
    for command in (ButtonCommand.PLAY_PAUSE, ButtonCommand.NEXT, ButtonCommand.STOP):
        await engine.speaker_button(SPEAKER.address, ButtonPress(command))
    await engine.close()


async def test_volume_keys_change_that_speakers_volume() -> None:
    engine, backend = await _engine()
    # Not playing there: the keys are ignored.
    await engine.speaker_button(SPEAKER.address, ButtonPress(ButtonCommand.VOLUME_UP))
    assert engine.outputs.prefs.get(SPEAKER.id).volume is None
    await engine.outputs.start(SPEAKER.id)
    await engine.speaker_button(SPEAKER.address, ButtonPress(ButtonCommand.VOLUME_UP))
    assert engine.outputs.prefs.get(SPEAKER.id).volume == 55
    await engine.speaker_button(SPEAKER.address, ButtonPress(ButtonCommand.VOLUME_DOWN))
    assert engine.outputs.prefs.get(SPEAKER.id).volume == 50
    await engine.speaker_button(SPEAKER.address, ButtonPress(ButtonCommand.VOLUME, 30.0))
    assert engine.outputs.prefs.get(SPEAKER.id).volume == 30
    await engine.speaker_button(SPEAKER.address, ButtonPress(ButtonCommand.VOLUME))
    assert engine.outputs.prefs.get(SPEAKER.id).volume == 30
    await engine.speaker_button("192.0.2.250", ButtonPress(ButtonCommand.VOLUME_UP))
    del backend
    await engine.close()


async def test_the_engine_starts_buttons_and_reannounces_them() -> None:
    advertiser = FakeAdvertiser()
    buttons = SpeakerButtons(advertiser, host="127.0.0.1")
    engine = Engine(FakeBackend([]), speaker_buttons=buttons)
    await engine.start_speaker_buttons()
    await engine.start_speaker_buttons()  # once only
    await engine.network_changed()
    assert len(advertiser.published) == 2  # again on the new addresses
    await engine.close()
    assert not buttons.running


async def test_a_busy_port_turns_buttons_off() -> None:
    blocker = SpeakerButtons(None, host="127.0.0.1")

    async def handler(_address: str, _press: ButtonPress) -> None:
        pass

    await blocker.start(handler)
    engine = Engine(
        FakeBackend([]), speaker_buttons=SpeakerButtons(None, host="127.0.0.1", port=blocker.port)
    )
    await engine.start_speaker_buttons()
    assert engine.speaker_buttons is not None
    assert not engine.speaker_buttons.running
    await engine.close()
    await blocker.stop()
    await asyncio.sleep(0)
