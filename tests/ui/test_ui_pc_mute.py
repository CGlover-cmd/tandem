"""The window's side of muting the PC while AirPlay plays (ADR-0020), on the demo."""

from __future__ import annotations

from typing import Any

from demo_harness import demo_backend, settle, until

from tandem.engine.adapters.demo import PATIO, PC_SPEAKERS
from tandem.ui.controller import AppController


def _pc(controller: AppController) -> dict[str, Any]:
    outputs = controller.snapshot()["audio"]["outputs"]
    return next(o for o in outputs if o["id"] == PC_SPEAKERS)


async def test_the_pc_shows_muted_and_can_be_turned_back_on() -> None:
    controller = AppController(demo_backend())
    await controller.start()
    assert _pc(controller)["state"] == "direct"
    assert controller.snapshot()["appearance"]["mutePc"] is True

    controller.handle({"type": "setOutput", "id": PATIO, "on": True})
    await settle(controller)
    await until(lambda: _pc(controller)["state"] == "muted")

    controller.handle({"type": "setOutput", "id": PC_SPEAKERS, "on": True})
    await settle(controller)
    await until(lambda: _pc(controller)["state"] == "ahead")

    controller.handle({"type": "setOutput", "id": PC_SPEAKERS, "on": False})
    await settle(controller)
    await until(lambda: _pc(controller)["state"] == "muted")

    controller.handle({"type": "setOutput", "id": PATIO, "on": False})
    await settle(controller)
    await until(lambda: _pc(controller)["state"] == "direct")
    await controller.stop()


async def test_the_setting_stops_the_muting() -> None:
    controller = AppController(demo_backend())
    await controller.start()
    controller.handle({"type": "setAppearance", "mutePc": False})
    await settle(controller)
    assert controller.snapshot()["appearance"]["mutePc"] is False
    controller.handle({"type": "setOutput", "id": PATIO, "on": True})
    await settle(controller)
    assert _pc(controller)["state"] == "direct"
    controller.handle({"type": "setAppearance", "mutePc": True})
    await settle(controller)
    await until(lambda: _pc(controller)["state"] == "muted")
    controller.handle({"type": "allOutputsOff"})
    await settle(controller)
    await until(lambda: _pc(controller)["state"] == "direct")
    await controller.stop()
