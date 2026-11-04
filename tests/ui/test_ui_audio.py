"""The Audio panel and Send to TV, on the demo backend (invented devices)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tandem.ui.audio_panel import Latest
from tandem.ui.backend import AudioError, AudioSourceChoice, MediaError, OutputState
from tandem.ui.controller import AppController
from tandem.ui.demo_audio import DEMO_DEFAULT_PC_OUTPUT
from tandem.ui.demo_backend import DemoBackend


async def _started(backend: DemoBackend, picker: Any = None) -> AppController:
    controller = AppController(backend, demo_mode=True, picker=picker)
    await controller.start()
    await controller.runner.drain()
    return controller


def _output(controller: AppController, output_id: str) -> dict[str, Any]:
    return next(o for o in controller.snapshot()["audio"]["outputs"] if o["id"] == output_id)


async def _connected_tv(controller: AppController) -> None:
    controller.pair("demo-tv")
    await controller.runner.drain()
    for pin in ("1234", "5678"):
        controller.pairing.submit_pin(pin)
        await controller.runner.drain()
    await controller.runner.drain()


async def test_outputs_turn_on_and_off(backend: DemoBackend) -> None:
    controller = await _started(backend)
    audio = controller.snapshot()["audio"]
    assert audio["source"] == "system"
    assert audio["pcOutputsHidden"]
    assert DEMO_DEFAULT_PC_OUTPUT not in [o["id"] for o in audio["outputs"]]
    assert not audio["canPickFiles"]

    controller.handle({"type": "setOutput", "id": "demo-speaker-1", "on": True})
    await controller.runner.drain()
    assert _output(controller, "demo-speaker-1")["state"] == "streaming"
    assert controller.snapshot()["audio"]["streaming"] == 1

    controller.handle({"type": "setOutputVolume", "id": "demo-speaker-1", "level": 35})
    controller.handle({"type": "setOutputDelay", "id": "demo-speaker-1", "ms": 800})
    controller.handle({"type": "setOutputDelay", "id": "demo-speaker-1", "ms": 20_000})  # bad
    controller.handle({"type": "setOutputVolume", "id": "demo-speaker-1", "level": True})  # bad
    await controller.runner.drain()
    speaker = _output(controller, "demo-speaker-1")
    assert (speaker["volume"], speaker["delayMs"]) == (35, 800)

    controller.handle({"type": "allOutputsOff"})
    await controller.runner.drain()
    assert controller.snapshot()["audio"]["streaming"] == 0


async def test_unpaired_tv_output_says_pair_first(backend: DemoBackend) -> None:
    controller = await _started(backend)
    assert _output(controller, "demo-tv")["needsPairing"]
    controller.handle({"type": "setOutput", "id": "demo-tv", "on": True})
    await controller.runner.drain()
    assert controller.message == {"code": "backend", "text": "Pair this device first."}
    with pytest.raises(AudioError):
        await backend.set_output("nope", True)


async def test_source_switch_shows_and_hides_the_default_pc_output(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.handle({"type": "setAudioSource", "source": "player"})
    controller.handle({"type": "setAudioSource", "source": "radio"})  # unknown: ignored
    await controller.runner.drain()
    ids = [o["id"] for o in controller.snapshot()["audio"]["outputs"]]
    assert DEMO_DEFAULT_PC_OUTPUT in ids
    controller.handle({"type": "setOutput", "id": DEMO_DEFAULT_PC_OUTPUT, "on": True})
    await controller.runner.drain()
    await backend.set_audio_source(AudioSourceChoice.SYSTEM)
    await controller.runner.drain()
    ids = [o["id"] for o in controller.snapshot()["audio"]["outputs"]]
    assert DEMO_DEFAULT_PC_OUTPUT not in ids


async def test_send_a_link_to_the_tv(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.handle({"type": "sendMedia", "id": "demo-tv", "location": "https://x.example/a.mp4"})
    await controller.runner.drain()
    assert controller.message == {"code": "backend", "text": "Connect the TV first."}
    await _connected_tv(controller)
    controller.handle({"type": "sendMedia", "id": "demo-tv", "location": "   "})  # empty: ignored
    controller.handle({"type": "sendMedia", "id": "demo-tv", "location": "x" * 3000})  # too long
    controller.handle({"type": "sendMedia", "id": "demo-tv", "location": "https://x.example/a.mp4"})
    await controller.runner.drain()
    tv = next(d for d in controller.snapshot()["devices"] if d["id"] == "demo-tv")
    assert tv["send"] == {"state": "playing", "title": "a.mp4"}
    assert backend.sent == [("demo-tv", "https://x.example/a.mp4")]

    controller.handle({"type": "stopMedia", "id": "demo-tv"})
    await controller.runner.drain()
    tv = next(d for d in controller.snapshot()["devices"] if d["id"] == "demo-tv")
    assert tv["send"] is None
    with pytest.raises(MediaError, match="Apple TV"):
        await backend.send_media("demo-speaker-1", "https://x.example/a.mp4")
    with pytest.raises(MediaError, match="Paste a link"):
        await backend.send_media("demo-tv", " ")


class _Picker:
    def __init__(self, path: str | None) -> None:
        self.path = path
        self.asked = 0

    async def pick_video(self) -> str | None:
        self.asked += 1
        return self.path


async def test_choosing_a_file_sends_it(backend: DemoBackend) -> None:
    picker = _Picker("C:/Videos/holiday.mov")
    controller = await _started(backend, picker)
    assert controller.snapshot()["audio"]["canPickFiles"]
    await _connected_tv(controller)
    controller.handle({"type": "pickMedia", "id": "demo-tv"})
    await controller.runner.drain()
    assert backend.sent == [("demo-tv", "C:/Videos/holiday.mov")]
    assert not controller.snapshot()["audio"]["picking"]

    picker.path = None  # cancelled
    controller.handle({"type": "pickMedia", "id": "demo-tv"})
    await controller.runner.drain()
    assert len(backend.sent) == 1
    assert picker.asked == 2


async def test_latest_sends_only_the_newest_value() -> None:
    sent: list[tuple[str, int]] = []
    gate = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []

    async def send(key: str, value: int) -> None:
        await gate.wait()
        sent.append((key, value))

    latest = Latest(lambda coro: tasks.append(asyncio.ensure_future(coro)), send)
    for value in (1, 2, 3, 4):
        latest.put("a", value)
        await asyncio.sleep(0)
    gate.set()
    await asyncio.gather(*tasks)
    assert sent == [("a", 1), ("a", 4)]


async def test_output_states_cover_the_failed_case(backend: DemoBackend) -> None:
    assert OutputState("failed") is OutputState.FAILED
