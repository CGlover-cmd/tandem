"""Finding a speaker by address and speaker passwords in the window, on the demo (ADR-0023)."""

from __future__ import annotations

from typing import Any

from demo_harness import settle, until

from tandem.bridge import DemoBackend
from tandem.engine.adapters.demo import HIDDEN, WRONG_PASSWORD
from tandem.ui.controller import AppController


async def _started(backend: DemoBackend) -> AppController:
    controller = AppController(backend, demo_mode=True)
    await controller.start()
    await settle(controller)
    return controller


def _network(controller: AppController) -> dict[str, Any]:
    return controller.snapshot()["network"]


def _message(controller: AppController) -> str | None:
    message = controller.snapshot()["message"]
    controller.dismiss_message()
    return None if message is None else message["code"]


def _output(controller: AppController, output_id: str) -> dict[str, Any] | None:
    outputs = controller.snapshot()["audio"]["outputs"]
    return next((o for o in outputs if o["id"] == output_id), None)


async def test_a_hidden_speaker_is_added_by_address(backend: DemoBackend) -> None:
    controller = await _started(backend)
    assert _network(controller) == {
        "addresses": [],
        "adding": False,
        "checking": False,
        "findings": None,
        "speakersSeen": 0,
    }
    assert controller.device(HIDDEN) is None
    for text, code in [
        ("speaker", "badAddress"),
        ("8.8.8.8", "notLocalAddress"),
        ("192.0.2.99", "noSpeakerThere"),
    ]:
        controller.handle({"type": "addSpeakerAddress", "address": text})
        await settle(controller)
        assert _message(controller) == code, text
    controller.handle({"type": "addSpeakerAddress", "address": "   "})  # ignored
    controller.handle({"type": "addSpeakerAddress", "address": " 192.0.2.60 "})
    await settle(controller)
    assert _network(controller)["addresses"] == ["192.0.2.60"]
    assert controller.device(HIDDEN) is not None
    controller.handle({"type": "removeSpeakerAddress", "address": "192.0.2.60"})
    controller.handle({"type": "removeSpeakerAddress"})  # malformed: ignored
    await settle(controller)
    assert _network(controller)["addresses"] == []
    await controller.stop()


async def test_a_speaker_with_a_password_asks_for_it(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.handle({"type": "addSpeakerAddress", "address": "192.0.2.60"})
    await settle(controller)
    controller.handle({"type": "setOutput", "id": HIDDEN, "on": True})
    await settle(controller)
    await until(lambda: (_output(controller, HIDDEN) or {}).get("state") == "failed")
    assert (_output(controller, HIDDEN) or {})["problem"] == "password"
    controller.handle({"type": "setSpeakerPassword", "id": HIDDEN, "password": ""})  # ignored
    controller.handle({"type": "setSpeakerPassword", "id": HIDDEN, "password": WRONG_PASSWORD})
    await settle(controller)
    await until(lambda: (_output(controller, HIDDEN) or {}).get("state") == "failed")
    assert (_output(controller, HIDDEN) or {})["problem"] == "password"
    controller.handle({"type": "setSpeakerPassword", "id": HIDDEN, "password": "open-sesame"})
    await settle(controller)
    await until(lambda: (_output(controller, HIDDEN) or {}).get("state") == "streaming")
    controller.handle({"type": "setSpeakerPassword", "id": "gone", "password": "x"})
    await settle(controller)
    assert _message(controller) == "speakerGone"
    await controller.stop()


async def test_the_network_check_reports_back(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.handle({"type": "checkNetwork"})
    await settle(controller)
    await until(lambda: _network(controller)["findings"] is not None)
    network = _network(controller)
    assert network["checking"] is False
    assert network["findings"] == []  # the demo's network is fine
    assert network["speakersSeen"] > 0
    await controller.stop()
