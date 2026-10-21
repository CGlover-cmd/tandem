from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from tandem.ui.backend import DeviceKind, DeviceSnapshot, LinkState, PairingError, PairingFlow
from tandem.ui.controller import AppController
from tandem.ui.demo_backend import WRONG_PIN, DemoBackend


async def _started(backend: DemoBackend) -> AppController:
    controller = AppController(backend, demo_mode=True)
    await controller.start()
    return controller


def _state(controller: AppController, device_id: str) -> LinkState:
    device = controller.device(device_id)
    assert device is not None
    return device.state


# Devices


async def test_start_lists_devices_sorted_by_name(backend: DemoBackend) -> None:
    controller = await _started(backend)

    names = [d["name"] for d in controller.snapshot()["devices"]]
    assert names == ["Den Soundbar", "Living Room TV", "Office Speaker", "Patio Speaker"]
    assert controller.discovering is False


async def test_sort_is_case_insensitive_then_by_id(backend: DemoBackend) -> None:
    controller = AppController(backend)
    for device in (
        DeviceSnapshot("b", "loft", DeviceKind.HOMEPOD),
        DeviceSnapshot("a", "Loft", DeviceKind.HOMEPOD),
        DeviceSnapshot("c", "Attic", DeviceKind.HOMEPOD),
    ):
        backend._set(device)  # pyright: ignore[reportPrivateUsage]
    await controller.start()

    assert [d.id for d in controller.devices() if d.id in "abc"] == ["c", "a", "b"]


async def test_snapshot_is_ready_for_json(backend: DemoBackend) -> None:
    controller = await _started(backend)

    snapshot = controller.snapshot()
    tv = next(d for d in snapshot["devices"] if d["id"] == "demo-tv")
    assert tv == {
        "id": "demo-tv",
        "name": "Living Room TV",
        "kind": "apple_tv",
        "state": "disconnected",
        "needsPairing": True,
        "retryIn": None,
    }
    assert snapshot["appearance"] == {"theme": "system", "background": "mist"}
    assert snapshot["pairing"]["state"] == "closed"
    assert snapshot["demo"] is True


async def test_listeners_hear_every_change_until_unsubscribed(backend: DemoBackend) -> None:
    controller = AppController(backend)
    calls: list[int] = []
    unsubscribe = controller.subscribe(lambda: calls.append(1))
    await controller.start()
    heard = len(calls)
    assert heard > 4

    unsubscribe()
    unsubscribe()  # twice is harmless
    backend.remove("demo-tv")
    assert len(calls) == heard


async def test_activate_connects_then_disconnects(backend: DemoBackend) -> None:
    controller = await _started(backend)

    controller.activate("demo-speaker-1")
    await controller.runner.drain()
    assert _state(controller, "demo-speaker-1") is LinkState.CONNECTED

    controller.activate("demo-speaker-1")
    await controller.runner.drain()
    assert _state(controller, "demo-speaker-1") is LinkState.DISCONNECTED


async def test_activate_unknown_device_does_nothing(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.activate("missing")
    controller.pair("missing")
    await controller.runner.drain()
    assert controller.pairing.state == "closed"


# Pairing


async def test_activate_on_unpaired_tv_opens_pairing(backend: DemoBackend) -> None:
    controller = await _started(backend)

    controller.activate("demo-tv")

    assert controller.pairing.state == "starting"
    assert controller.pairing.device_name == "Living Room TV"
    await controller.runner.drain()
    assert controller.pairing.state == "enterPin"


async def test_pairing_retries_wrong_pin_then_connects(backend: DemoBackend) -> None:
    controller = await _started(backend)
    pairing = controller.pairing
    controller.pair("demo-tv")
    await controller.runner.drain()

    pairing.submit_pin(WRONG_PIN)
    await controller.runner.drain()
    assert pairing.state == "enterPin"
    assert pairing.error == {"code": "wrongPin"}

    pairing.submit_pin(" 4821 ")
    await controller.runner.drain()
    assert pairing.state == "done"
    assert pairing.error is None
    tv = controller.device("demo-tv")
    assert tv is not None
    assert not tv.needs_pairing
    assert tv.state is LinkState.CONNECTED  # pairing connects straight away

    pairing.close()
    assert pairing.state == "closed"


async def test_pin_must_be_four_digits(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.pair("demo-tv")
    await controller.runner.drain()

    controller.pairing.submit_pin("12a")

    assert controller.pairing.state == "enterPin"
    assert controller.pairing.error == {"code": "pinFormat"}


async def test_pin_is_ignored_when_not_asked_for(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.pairing.submit_pin("1234")
    assert controller.pairing.state == "closed"


async def test_opening_twice_keeps_the_first_sheet(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.pair("demo-tv")
    controller.pairing.open("demo-speaker-1", "Patio Speaker")
    assert controller.pairing.device_id == "demo-tv"
    await controller.runner.drain()


async def test_cancel_while_starting_ignores_the_late_result(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.pair("demo-tv")

    controller.pairing.cancel()
    await controller.runner.drain()

    assert controller.pairing.state == "closed"


async def test_cancel_while_entering_pin_cancels_the_flow(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.pair("demo-tv")
    await controller.runner.drain()

    controller.pairing.cancel()
    await controller.runner.drain()

    assert controller.pairing.state == "closed"
    tv = controller.device("demo-tv")
    assert tv is not None
    assert tv.needs_pairing


async def test_closing_while_checking_ignores_the_late_result(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.pair("demo-tv")
    await controller.runner.drain()
    controller.pairing.submit_pin("1234")

    controller.pairing.close()
    await controller.runner.drain()

    assert controller.pairing.state == "closed"


async def test_pairing_that_cannot_start_shows_failed(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.pairing.open("demo-speaker-1", "Patio Speaker")
    await controller.runner.drain()

    assert controller.pairing.state == "failed"
    error = controller.pairing.error
    assert error is not None
    assert error["code"] == "pairingFailed"
    assert error["text"] == "This device doesn't need pairing."


async def test_device_leaving_closes_its_pairing_sheet(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.pair("demo-tv")
    await controller.runner.drain()

    backend.remove("demo-tv")

    assert controller.pairing.state == "closed"
    assert controller.device("demo-tv") is None


class _FailingSubmit:
    async def submit_pin(self, pin: str) -> None:
        raise PairingError("")

    async def cancel(self) -> None:
        return None


class _BrokenBackend(DemoBackend):
    async def connect(self, device_id: str) -> None:
        raise OSError("connection refused by 192.0.2.10")

    async def begin_pairing(self, device_id: str) -> PairingFlow:
        return _FailingSubmit()


async def _no_wait(_seconds: float) -> None:
    await asyncio.sleep(0)


async def test_pairing_error_without_text_still_fails() -> None:
    controller = await _started(_BrokenBackend(sleep=_no_wait))
    controller.pair("demo-tv")
    await controller.runner.drain()

    controller.pairing.submit_pin("1234")
    await controller.runner.drain()

    assert controller.pairing.state == "failed"
    assert controller.pairing.error == {"code": "pairingFailed"}


async def test_unexpected_errors_show_a_generic_message_and_log_no_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    controller = await _started(_BrokenBackend(sleep=_no_wait))

    with caplog.at_level(logging.ERROR):
        controller.activate("demo-speaker-1")
        await controller.runner.drain()

    assert controller.message == {"code": "taskFailed"}
    assert "192.0.2.10" not in caplog.text
    assert "OSError" in caplog.text

    controller.dismiss_message()
    assert controller.message is None


async def test_backend_pairing_errors_are_shown_as_given(backend: DemoBackend) -> None:
    controller = await _started(backend)

    controller.connect("demo-tv")  # not paired yet
    await controller.runner.drain()

    assert controller.message == {"code": "backend", "text": "Pair this device first."}


# Appearance


async def test_set_appearance_saves_and_updates(backend: DemoBackend) -> None:
    controller = await _started(backend)

    controller.set_appearance("dark", "sky")
    await controller.runner.drain()

    assert controller.snapshot()["appearance"] == {"theme": "dark", "background": "sky"}


async def test_unknown_appearance_is_ignored(
    backend: DemoBackend, caplog: pytest.LogCaptureFixture
) -> None:
    controller = await _started(backend)

    controller.set_appearance("neon", "sky")
    controller.set_appearance("dark", "plaid")
    await controller.runner.drain()

    assert controller.snapshot()["appearance"] == {"theme": "system", "background": "mist"}
    assert "unknown appearance" in caplog.text


# Commands from the front end


@pytest.mark.parametrize(
    "command",
    [
        {},
        {"type": "nonsense"},
        {"type": "connect"},
        {"type": "connect", "id": 7},
        {"type": "submitPin", "pin": 1234},
        {"type": "setAppearance", "theme": 3},
    ],
)
async def test_malformed_commands_are_ignored(
    backend: DemoBackend, command: dict[str, Any]
) -> None:
    controller = await _started(backend)
    before = controller.snapshot()

    controller.handle(command)
    await controller.runner.drain()

    assert controller.snapshot() == before


async def test_commands_drive_the_controller(backend: DemoBackend) -> None:
    controller = await _started(backend)

    controller.handle({"type": "connect", "id": "demo-speaker-2"})
    await controller.runner.drain()
    assert _state(controller, "demo-speaker-2") is LinkState.CONNECTED

    controller.handle({"type": "disconnect", "id": "demo-speaker-2"})
    controller.handle({"type": "activate", "id": "demo-speaker-1"})
    await controller.runner.drain()
    assert _state(controller, "demo-speaker-2") is LinkState.DISCONNECTED
    assert _state(controller, "demo-speaker-1") is LinkState.CONNECTED

    controller.handle({"type": "pair", "id": "demo-tv"})
    await controller.runner.drain()
    controller.handle({"type": "submitPin", "pin": "1234"})
    await controller.runner.drain()
    assert controller.pairing.state == "done"
    controller.handle({"type": "closePairing"})
    assert controller.pairing.state == "closed"

    controller.handle({"type": "pair", "id": "demo-tv"})  # already paired: fails
    await controller.runner.drain()
    controller.handle({"type": "cancelPairing"})
    assert controller.pairing.state == "closed"

    controller.handle({"type": "setAppearance", "background": "meadow"})
    await controller.runner.drain()
    assert controller.appearance.background == "meadow"

    controller.message = {"code": "taskFailed"}
    controller.handle({"type": "dismissMessage"})
    assert controller.message is None


async def test_stop_unsubscribes(backend: DemoBackend) -> None:
    controller = await _started(backend)
    await controller.stop()

    backend.remove("demo-speaker-1")

    assert controller.device("demo-speaker-1") is not None
