"""The Audio and Send to TV panels on the real engine. Devices and paths are invented."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from conftest import FakeBackend, ManualSleep, make_device
from tandem import bridge, bridge_audio
from tandem.engine.events import EventBus
from tandem.engine.models import DeviceKind, Service
from tandem.engine.output_prefs import OutputPrefsStore
from tandem.engine.service import Engine
from tandem.engine.settings import SettingsStore
from tandem.ui import backend as ui

TV = make_device(
    id="AA:BB:CC:00:00:02",
    name="Living Room TV",
    kind=DeviceKind.APPLE_TV,
    address="127.0.0.1",
    services=frozenset({Service.AIRPLAY, Service.COMPANION}),
)
SPEAKER = make_device()
UNPAIRED = make_device(
    id="AA:BB:CC:00:00:03",
    name="Garden Speaker",
    needs_pairing=frozenset({Service.AIRPLAY}),
)
REMOTE_ONLY = make_device(
    id="AA:BB:CC:00:00:04", name="Hall Remote", services=frozenset({Service.COMPANION})
)


class Harness:
    def __init__(self, tmp_path: Path, sleep: ManualSleep) -> None:
        self.fake = FakeBackend([TV, SPEAKER, UNPAIRED, REMOTE_ONLY])
        bus = EventBus()
        self.prefs_file = tmp_path / "outputs.json"
        self.prefs = OutputPrefsStore(self.prefs_file)
        self.engine = Engine(self.fake, bus=bus, sleep=sleep, discovery_interval=60.0)
        self.backend = bridge.EngineBackend(
            self.engine, SettingsStore(tmp_path / "settings.json", bus), output_prefs=self.prefs
        )
        self.events: list[ui.BackendEvent] = []
        self.backend.subscribe(self.events.append)

    def output(self, output_id: str) -> ui.OutputSnapshot:
        return next(o for o in self.backend.audio().outputs if o.id == output_id)


@pytest.fixture
async def harness(tmp_path: Path, manual_sleep: ManualSleep) -> AsyncIterator[Harness]:
    h = Harness(tmp_path, manual_sleep)
    await h.backend.start()
    yield h
    manual_sleep.release()
    await h.backend.stop()


async def _until(predicate: object) -> None:
    for _ in range(500):
        if callable(predicate) and predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition not reached")


async def test_outputs_list_audio_devices_then_pc_outputs(harness: Harness) -> None:
    audio = harness.backend.audio()
    ids = [o.id for o in audio.outputs]
    # By name, then the PC: Windows' default output first (Windows plays there itself).
    assert ids == [UNPAIRED.id, SPEAKER.id, TV.id, "local:speakers", "local:headphones"]
    assert harness.output("local:speakers").state is ui.OutputState.DIRECT
    assert audio.source is ui.AudioSourceChoice.SYSTEM
    assert audio.pc_outputs_hidden
    assert harness.output(UNPAIRED.id).needs_pairing
    assert harness.output(SPEAKER.id).device_kind is ui.DeviceKind.HOMEPOD
    assert harness.output("local:headphones").kind is ui.OutputKind.PC


async def test_turning_outputs_on_and_off(harness: Harness) -> None:
    await harness.backend.set_output_volume(SPEAKER.id, 30)  # saved before it's on
    await harness.backend.set_output_delay(SPEAKER.id, 1200)
    await harness.backend.set_output(SPEAKER.id, True)
    await _until(lambda: harness.output(SPEAKER.id).state is ui.OutputState.STREAMING)
    speaker = harness.output(SPEAKER.id)
    assert (speaker.volume, speaker.delay_ms) == (30, 1200)
    assert harness.fake.sinks[SPEAKER.id][0].volumes == [30]

    await harness.backend.set_output_volume(SPEAKER.id, 55)
    await harness.backend.set_output_delay(SPEAKER.id, 99_999)
    assert harness.output(SPEAKER.id).delay_ms == ui.MAX_DELAY_MS
    assert harness.fake.sinks[SPEAKER.id][0].volumes[-1] == 55
    saved = json.loads(harness.prefs_file.read_text(encoding="utf-8"))
    assert saved[SPEAKER.id] == {"volume": 55.0, "delay_ms": ui.MAX_DELAY_MS, "on": True}

    await harness.backend.set_output("local:headphones", True)
    assert harness.output("local:headphones").state is not ui.OutputState.OFF
    await harness.backend.set_output(SPEAKER.id, False)
    assert harness.output(SPEAKER.id).state is ui.OutputState.OFF
    assert any(isinstance(e, ui.AudioChanged) for e in harness.events)


async def test_output_problems_are_worded(harness: Harness) -> None:
    with pytest.raises(ui.AudioError, match="Pair this device first"):
        await harness.backend.set_output(UNPAIRED.id, True)
    with pytest.raises(ui.AudioError, match="no longer available"):
        await harness.backend.set_output("AA:BB:CC:00:00:99", True)
    with pytest.raises(ui.AudioError, match="couldn't send audio"):
        await harness.backend.set_output("local:speakers", True)  # would echo: not offered
    assert harness.output("local:headphones").state is ui.OutputState.OFF


async def test_a_failed_stream_shows_until_tried_again(harness: Harness) -> None:
    harness.fake.audio_enabled = False  # the device takes no audio
    await harness.backend.set_output(SPEAKER.id, True)
    await _until(lambda: harness.output(SPEAKER.id).state is ui.OutputState.FAILED)
    await harness.backend.set_output(SPEAKER.id, False)
    assert harness.output(SPEAKER.id).state is ui.OutputState.OFF


async def test_source_switch(harness: Harness) -> None:
    await harness.backend.set_audio_source(ui.AudioSourceChoice.PLAYER)
    audio = harness.backend.audio()
    assert audio.source is ui.AudioSourceChoice.PLAYER
    assert not audio.pc_outputs_hidden
    assert "local:speakers" in [o.id for o in audio.outputs]


async def test_send_media_and_stop(harness: Harness, tmp_path: Path) -> None:
    await harness.backend.send_media(TV.id, "https://media.example/clip.mp4")
    await _until(
        lambda: (
            (send := harness.backend.send(TV.id)) is not None and send.state is ui.SendState.PLAYING
        )
    )
    send = harness.backend.send(TV.id)
    assert send == ui.SendSnapshot(ui.SendState.PLAYING, "clip.mp4")
    await harness.backend.stop_media(TV.id)
    assert harness.backend.send(TV.id) is None
    assert ui.SendChanged(TV.id, None) in harness.events
    await harness.backend.stop_media(TV.id)  # nothing to stop: no event

    with pytest.raises(ui.MediaError, match="isn't there"):
        await harness.backend.send_media(TV.id, str(tmp_path / "gone.mp4"))
    with pytest.raises(ui.MediaError, match="no longer available"):
        await harness.backend.send_media("AA:BB:CC:00:00:99", "https://media.example/a.mp4")


async def test_send_network_failure_is_worded(harness: Harness) -> None:
    async def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("no route to 192.0.2.1")

    harness.engine.play_media = refuse  # type: ignore[method-assign]
    with pytest.raises(ui.MediaError) as failed:
        await harness.backend.send_media(TV.id, "https://media.example/a.mp4")
    assert str(failed.value) == bridge_audio.NO_SEND


def test_prefs_store_survives_bad_files(tmp_path: Path) -> None:
    path = tmp_path / "outputs.json"
    store = OutputPrefsStore(path)
    store.load()  # missing: fine
    path.write_text("{not json", encoding="utf-8")
    store.load()
    path.write_text("[1, 2]", encoding="utf-8")
    store.load()
    path.write_text(
        json.dumps(
            {
                "a": {"volume": 40, "delay_ms": 300},
                "b": {"volume": 400, "delay_ms": -5},
                "c": "junk",
                "d": {"volume": True, "delay_ms": True},
            }
        ),
        encoding="utf-8",
    )
    store.load()
    assert (store.get("a").volume, store.get("a").delay_ms) == (40.0, 300)
    assert (store.get("b").volume, store.get("b").delay_ms) == (None, 0)
    assert store.get("c").volume is None
    assert store.get("d").delay_ms == 0
    assert store.update("a", volume=40) == store.get("a")  # unchanged: no write needed
    memory = OutputPrefsStore(None)
    memory.load()
    assert memory.update("x", delay_ms=5).delay_ms == 5


async def test_an_output_shows_starting_at_once(harness: Harness) -> None:
    # 1.0.0 showed nothing until the speaker answered, which could take half a minute.
    seen: list[ui.OutputState] = []

    def record(event: ui.BackendEvent) -> None:
        if isinstance(event, ui.AudioChanged):
            seen.extend(o.state for o in event.audio.outputs if o.id == SPEAKER.id)

    harness.backend.subscribe(record)
    await harness.backend.set_output(SPEAKER.id, True)
    assert seen[0] is ui.OutputState.STARTING


async def test_a_speaker_that_cant_connect_fails_and_stops_trying(harness: Harness) -> None:
    harness.fake.connect_failures[SPEAKER.id] = [OSError("refused") for _ in range(50)]
    harness.engine.audio_connect_timeout = 0.05
    with pytest.raises(ui.AudioError):
        await harness.backend.set_output(SPEAKER.id, True)
    assert harness.output(SPEAKER.id).state is ui.OutputState.FAILED
