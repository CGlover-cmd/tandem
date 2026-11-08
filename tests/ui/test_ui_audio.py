"""The Audio panel and Send to TV, on the demo backend (invented devices)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from demo_harness import settle

from tandem.bridge import DemoBackend
from tandem.engine.adapters.demo import PC_SPEAKERS as DEMO_DEFAULT_PC_OUTPUT
from tandem.ui.audio_panel import Latest
from tandem.ui.backend import AudioError, AudioSourceChoice, MediaError, OutputState
from tandem.ui.controller import AppController


async def _started(backend: DemoBackend, picker: Any = None) -> AppController:
    controller = AppController(backend, demo_mode=True, picker=picker)
    await controller.start()
    await settle(controller)
    return controller


def _output(controller: AppController, output_id: str) -> dict[str, Any]:
    return next(o for o in controller.snapshot()["audio"]["outputs"] if o["id"] == output_id)


async def _connected_tv(controller: AppController) -> None:
    controller.pair("demo-tv")
    await settle(controller)
    for pin in ("1234", "5678"):
        controller.pairing.submit_pin(pin)
        await settle(controller)
    await settle(controller)


async def test_outputs_turn_on_and_off(backend: DemoBackend) -> None:
    controller = await _started(backend)
    audio = controller.snapshot()["audio"]
    assert audio["source"] == "system"
    assert audio["pcOutputsHidden"]
    # Windows plays to its default output itself: shown as on, and not counted as playing.
    assert _output(controller, DEMO_DEFAULT_PC_OUTPUT)["state"] == "direct"
    assert audio["streaming"] == 0
    assert not audio["canPickFiles"]

    controller.handle({"type": "setOutput", "id": "demo-speaker-1", "on": True})
    await settle(controller)
    assert _output(controller, "demo-speaker-1")["state"] == "streaming"
    assert controller.snapshot()["audio"]["streaming"] == 1

    controller.handle({"type": "setOutputVolume", "id": "demo-speaker-1", "level": 35})
    controller.handle({"type": "setOutputDelay", "id": "demo-speaker-1", "ms": 800})
    controller.handle({"type": "setOutputDelay", "id": "demo-speaker-1", "ms": 20_000})  # bad
    controller.handle({"type": "setOutputVolume", "id": "demo-speaker-1", "level": True})  # bad
    await settle(controller)
    speaker = _output(controller, "demo-speaker-1")
    assert (speaker["volume"], speaker["delayMs"]) == (35, 800)

    controller.handle({"type": "allOutputsOff"})
    await settle(controller)
    assert controller.snapshot()["audio"]["streaming"] == 0


async def test_unpaired_tv_output_says_pair_first(backend: DemoBackend) -> None:
    controller = await _started(backend)
    assert _output(controller, "demo-tv")["needsPairing"]
    controller.handle({"type": "setOutput", "id": "demo-tv", "on": True})
    await settle(controller)
    assert controller.message == {"code": "pairFirst"}
    with pytest.raises(AudioError):
        await backend.set_output("nope", True)


async def test_source_switch_shows_and_hides_the_default_pc_output(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.handle({"type": "setAudioSource", "source": "player"})
    controller.handle({"type": "setAudioSource", "source": "radio"})  # unknown: ignored
    await settle(controller)
    assert _output(controller, DEMO_DEFAULT_PC_OUTPUT)["state"] == "off"
    controller.handle({"type": "setOutput", "id": DEMO_DEFAULT_PC_OUTPUT, "on": True})
    await settle(controller)
    await backend.set_audio_source(AudioSourceChoice.SYSTEM)
    await settle(controller)
    assert _output(controller, DEMO_DEFAULT_PC_OUTPUT)["state"] == "direct"


async def test_send_a_link_to_the_tv(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.handle({"type": "sendMedia", "id": "demo-tv", "location": "https://x.example/a.mp4"})
    await settle(controller)
    assert controller.message == {"code": "pairFirst"}
    await _connected_tv(controller)
    controller.handle({"type": "sendMedia", "id": "demo-tv", "location": "   "})  # empty: ignored
    controller.handle({"type": "sendMedia", "id": "demo-tv", "location": "x" * 3000})  # too long
    controller.handle({"type": "sendMedia", "id": "demo-tv", "location": "https://x.example/a.mp4"})
    await settle(controller)
    tv = next(d for d in controller.snapshot()["devices"] if d["id"] == "demo-tv")
    assert tv["send"] == {"state": "playing", "title": "a.mp4"}
    assert backend.demo.sent == [("demo-tv", "https://x.example/a.mp4")]

    controller.handle({"type": "stopMedia", "id": "demo-tv"})
    await settle(controller)
    tv = next(d for d in controller.snapshot()["devices"] if d["id"] == "demo-tv")
    assert tv["send"] is None
    with pytest.raises(MediaError, match="notATv"):
        await backend.send_media("demo-speaker-1", "https://x.example/a.mp4")
    with pytest.raises(MediaError, match="noLocation"):
        await backend.send_media("demo-tv", " ")


class _Picker:
    def __init__(self, path: str | None) -> None:
        self.path = path
        self.asked = 0

    async def pick_video(self) -> str | None:
        self.asked += 1
        return self.path


async def test_choosing_a_file_sends_it(backend: DemoBackend, tmp_path: Path) -> None:
    video = tmp_path / "holiday.mov"
    video.write_bytes(b"invented")
    picker = _Picker(str(video))
    controller = await _started(backend, picker)
    assert controller.snapshot()["audio"]["canPickFiles"]
    await _connected_tv(controller)
    controller.handle({"type": "pickMedia", "id": "demo-tv"})
    await settle(controller)
    ((device_id, url),) = backend.demo.sent
    assert device_id == "demo-tv"
    assert url.startswith("http://")  # served to the TV from this PC
    tv = next(d for d in controller.snapshot()["devices"] if d["id"] == "demo-tv")
    assert tv["send"] == {"state": "playing", "title": "holiday.mov"}
    assert not controller.snapshot()["audio"]["picking"]

    picker.path = None  # cancelled
    controller.handle({"type": "pickMedia", "id": "demo-tv"})
    await settle(controller)
    assert len(backend.demo.sent) == 1
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


async def test_window_picker_without_a_window_returns_nothing() -> None:
    from tandem.ui.file_picker import WindowFilePicker

    picker = WindowFilePicker()
    assert await picker.pick_video() is None


async def test_closing_the_checklist_is_remembered(backend: DemoBackend) -> None:
    controller = await _started(backend)
    assert controller.snapshot()["appearance"]["onboarded"] is False
    controller.handle({"type": "setAppearance", "onboarded": True})
    controller.handle({"type": "setAppearance", "onboarded": "yes"})  # bad: ignored
    await settle(controller)
    assert controller.snapshot()["appearance"]["onboarded"] is True
    assert controller.snapshot()["appearance"]["background"] == "sky"  # kept


async def test_home_bridge_toggle_in_the_demo(backend: DemoBackend) -> None:
    controller = await _started(backend)
    assert controller.snapshot()["home"]["enabled"] is False
    controller.handle({"type": "setHomeBridge", "on": True})
    await settle(controller)
    home = controller.snapshot()["home"]
    assert (home["running"], home["setupCode"]) == (True, "123-45-678")
    assert next(s["name"] for s in home["switches"]) == "Tandem Audio"
    controller.handle({"type": "setHomeBridge", "on": False})
    await settle(controller)
    assert controller.snapshot()["home"]["running"] is False


def test_single_instance_claim() -> None:
    from tandem.ui.platform import claim_single_instance

    name = r"Local\TandemTestInstance"
    assert claim_single_instance(name)
    assert not claim_single_instance(name)  # a second copy is told to exit
