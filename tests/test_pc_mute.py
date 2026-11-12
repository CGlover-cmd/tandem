"""Muting the PC's own speakers while AirPlay plays (ADR-0020), with fake Windows speakers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from conftest import FakeBackend, FakeSpeakerMute, make_device
from tandem.engine.adapters import process_loopback
from tandem.engine.audio import AudioError
from tandem.engine.outputs import OutputError, OutputState
from tandem.engine.pc_mute import PcMute
from tandem.engine.service import AudioSource, Engine

PATIO = make_device(id="AA:BB:CC:00:00:31", name="Patio Speaker")
PC = "local:speakers"  # FakeBackend's default output
SPEAKERS = "endpoint-speakers"  # the same output, as Windows names it


async def _engine(**kwargs: object) -> tuple[Engine, FakeSpeakerMute]:
    backend = FakeBackend([PATIO])
    engine = Engine(backend, **kwargs)  # type: ignore[arg-type]
    await engine.open()
    await engine.scan()
    assert backend.speakers is not None
    return engine, backend.speakers


async def _until(check: Callable[[], bool], timeout: float = 3.0) -> None:
    """Wait in real time: the mute runs on a worker thread, and on Windows a short
    `asyncio.sleep` can return at once (its timers are as coarse as the clock)."""
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not check():
        if loop.time() > end:
            raise AssertionError("never happened")
        await asyncio.sleep(0.02)


def _pc(engine: Engine) -> OutputState:
    return next(s for s in engine.outputs.statuses() if s.id == PC).state


async def test_airplay_mutes_the_pc_and_unmutes_it_after() -> None:
    engine, speakers = await _engine()
    assert _pc(engine) is OutputState.DIRECT
    await engine.outputs.start(PATIO.id)
    await _until(lambda: speakers.outputs[SPEAKERS])
    assert _pc(engine) is OutputState.MUTED
    await engine.outputs.stop(PATIO.id)
    await _until(lambda: not speakers.outputs[SPEAKERS])
    assert _pc(engine) is OutputState.DIRECT
    await engine.close()


async def test_a_pc_the_user_muted_is_left_alone() -> None:
    engine, speakers = await _engine()
    speakers.outputs[SPEAKERS] = True
    await engine.outputs.start(PATIO.id)
    await asyncio.sleep(0.05)
    await engine.outputs.stop(PATIO.id)
    await asyncio.sleep(0.05)
    assert speakers.outputs[SPEAKERS] is True  # still the user's mute
    assert speakers.calls == []
    await engine.close()


async def test_the_pc_can_be_turned_back_on_while_airplay_plays() -> None:
    engine, speakers = await _engine()
    await engine.outputs.start(PATIO.id)
    await _until(lambda: _pc(engine) is OutputState.MUTED)
    await engine.outputs.start(PC)  # the PC's switch, on: hear both
    await _until(lambda: not speakers.outputs[SPEAKERS])
    assert _pc(engine) is OutputState.AHEAD
    await engine.outputs.stop(PC)  # off again: muted
    await _until(lambda: speakers.outputs[SPEAKERS])
    # Kept on lasts until AirPlay stops; the next time it mutes again.
    await engine.outputs.start(PC)
    await engine.outputs.stop(PATIO.id)
    await _until(lambda: _pc(engine) is OutputState.DIRECT)
    await engine.outputs.start(PATIO.id)
    await _until(lambda: _pc(engine) is OutputState.MUTED)
    await engine.close()


async def test_the_pc_switch_is_refused_while_airplay_is_off() -> None:
    engine, speakers = await _engine()
    with pytest.raises(OutputError) as refused:
        await engine.outputs.start(PC)  # Tandem would only echo Windows
    assert refused.value.reason == OutputError.NO_AUDIO
    await engine.outputs.stop(PC)  # harmless
    assert _pc(engine) is OutputState.DIRECT
    assert speakers.calls == []
    await engine.close()


async def test_the_setting_turns_it_off_and_on() -> None:
    engine, speakers = await _engine()
    await engine.outputs.start(PATIO.id)
    await _until(lambda: speakers.outputs[SPEAKERS])
    engine.outputs.set_pc_mute(False)
    await _until(lambda: not speakers.outputs[SPEAKERS])
    assert _pc(engine) is OutputState.DIRECT
    engine.outputs.set_pc_mute(True)
    await _until(lambda: speakers.outputs[SPEAKERS])
    await engine.close()
    assert not speakers.outputs[SPEAKERS]  # closing never leaves the PC muted


async def test_only_the_pcs_own_sound_mutes_it() -> None:
    engine, speakers = await _engine()
    await engine.set_audio_source(AudioSource.PLAYER)
    await engine.outputs.start(PATIO.id)
    await asyncio.sleep(0.05)
    assert speakers.calls == []  # Windows isn't playing what AirPlay plays
    await engine.set_audio_source(AudioSource.SYSTEM)
    await _until(lambda: speakers.outputs[SPEAKERS])
    await engine.set_audio_source(AudioSource.PLAYER)
    await _until(lambda: not speakers.outputs[SPEAKERS])
    await engine.close()


async def test_a_new_default_output_is_muted_instead() -> None:
    engine, speakers = await _engine()
    await engine.outputs.start(PATIO.id)
    await _until(lambda: speakers.outputs[SPEAKERS])
    speakers.default = "endpoint-headphones"  # headphones plugged in: Windows switches
    engine.outputs.refresh()
    await _until(lambda: speakers.outputs.get("endpoint-headphones", False))
    assert not speakers.outputs[SPEAKERS]
    await engine.close()


async def test_nothing_is_muted_when_the_capture_would_follow_the_mute() -> None:
    engine, speakers = await _engine()
    speakers.allowed = False  # classic loopback: a mute would silence AirPlay too
    await engine.outputs.start(PATIO.id)
    await asyncio.sleep(0.05)
    assert speakers.calls == []
    assert _pc(engine) is OutputState.DIRECT
    await engine.close()


async def test_falling_back_to_classic_capture_unmutes() -> None:
    engine, speakers = await _engine()
    await engine.outputs.start(PATIO.id)
    await _until(lambda: speakers.outputs[SPEAKERS])
    speakers.allowed = False
    engine.outputs.refresh()
    await _until(lambda: not speakers.outputs[SPEAKERS])
    await engine.close()


async def test_windows_refusing_is_not_fatal() -> None:
    engine, speakers = await _engine()
    speakers.fail = OSError("access denied")
    await engine.outputs.start(PATIO.id)
    await asyncio.sleep(0.05)
    assert engine.outputs.streaming() == [PATIO.id]  # AirPlay plays all the same
    speakers.fail = None
    await engine.close()


async def test_no_speaker_mute_at_all() -> None:
    backend = FakeBackend([PATIO])
    backend.speakers = None
    engine = Engine(backend)
    await engine.open()
    await engine.scan()
    await engine.outputs.start(PATIO.id)
    assert _pc(engine) is OutputState.DIRECT
    await engine.close()


async def test_a_mute_left_by_a_stopped_tandem_is_undone(tmp_path: Path) -> None:
    record = tmp_path / "pc-mute.json"
    engine, speakers = await _engine(pc_mute_record=record)
    await engine.outputs.start(PATIO.id)
    await _until(lambda: speakers.outputs[SPEAKERS])
    assert json.loads(record.read_text(encoding="utf-8")) == {"muted": SPEAKERS}
    # Tandem is stopped here without closing (a crash). The next start unmutes.
    after = PcMute(speakers, record)
    await after.recover()
    assert not speakers.outputs[SPEAKERS]
    assert not record.exists()


async def test_a_clean_stop_leaves_no_record(tmp_path: Path) -> None:
    record = tmp_path / "pc-mute.json"
    engine, speakers = await _engine(pc_mute_record=record)
    await engine.outputs.start(PATIO.id)
    await _until(lambda: record.exists())
    await engine.close()
    assert not record.exists()
    assert not speakers.outputs[SPEAKERS]


@pytest.mark.parametrize("content", ["not json", "[]", '{"muted": 3}', '{"muted": ""}'])
async def test_a_damaged_record_is_ignored(tmp_path: Path, content: str) -> None:
    record = tmp_path / "pc-mute.json"
    record.write_text(content, encoding="utf-8")
    speakers = FakeSpeakerMute()
    await PcMute(speakers, record).recover()
    assert speakers.calls == []


async def test_recovering_without_windows_speakers_just_forgets(tmp_path: Path) -> None:
    record = tmp_path / "pc-mute.json"
    record.write_text('{"muted": "endpoint-speakers"}', encoding="utf-8")
    await PcMute(None, record).recover()
    assert not record.exists()


async def test_recovering_survives_windows_refusing(tmp_path: Path) -> None:
    record = tmp_path / "pc-mute.json"
    record.write_text('{"muted": "endpoint-speakers"}', encoding="utf-8")
    speakers = FakeSpeakerMute()
    speakers.fail = OSError("gone")
    await PcMute(speakers, record).recover()
    assert not record.exists()


async def test_an_unwritable_record_does_not_stop_the_mute(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    speakers = FakeSpeakerMute()
    mute = PcMute(speakers, blocker / "pc-mute.json")  # its folder is a file
    assert await mute.apply(True)
    assert speakers.outputs[SPEAKERS]
    assert await mute.apply(False)
    assert not speakers.outputs[SPEAKERS]


class _Capture:
    def __init__(self, fails: bool = False) -> None:
        self.fails = fails
        self.running = False

    def start(self, on_pcm: Callable[[bytes], None]) -> None:
        if self.fails:
            raise AudioError("no process loopback here")
        self.running = True

    def stop(self) -> None:
        self.running = False


def test_the_capture_falls_back_to_classic_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[_Capture] = []

    def make(fails: bool) -> Callable[[], _Capture]:
        def factory() -> _Capture:
            made.append(_Capture(fails))
            return made[-1]

        return factory

    monkeypatch.setattr(process_loopback, "ProcessLoopbackCapture", make(True))
    monkeypatch.setattr(process_loopback, "LoopbackCapture", make(False))
    mode = process_loopback.CaptureMode(process=True)
    capture = process_loopback.SystemCapture(mode)
    capture.start(lambda _pcm: None)
    capture.start(lambda _pcm: None)  # already running: nothing new
    assert not mode.process  # Tandem stops muting the PC from now on
    assert [c.running for c in made] == [False, True]
    capture.stop()
    assert not made[1].running
    capture.stop()


def test_the_capture_uses_process_loopback_while_it_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_loopback, "ProcessLoopbackCapture", _Capture)
    mode = process_loopback.CaptureMode(process=True)
    capture = process_loopback.SystemCapture(mode)
    capture.start(lambda _pcm: None)
    assert mode.process


def test_process_loopback_needs_windows_10_2004(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_loopback.sys, "platform", "linux")
    assert not process_loopback.supported()
    assert not process_loopback.CaptureMode().process
