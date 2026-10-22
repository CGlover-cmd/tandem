from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from tandem.ui.backend import (
    MAX_TEXT,
    AppInfo,
    ControlError,
    DeviceKind,
    DeviceSnapshot,
    KeyAction,
    LinkState,
    PairingError,
    PairingFlow,
    RemoteKey,
)
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
        "controls": None,
        "apps": None,
    }
    assert snapshot["appearance"] == {
        "theme": "system",
        "background": "mist",
        "appIcons": True,
    }
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

    assert pairing.snapshot()["step"] == 1
    assert pairing.snapshot()["steps"] == 2

    pairing.submit_pin(" 4821 ")
    await controller.runner.drain()
    assert pairing.state == "enterPin"  # the TV shows its second PIN (AirPlay)
    assert pairing.step == 2
    tv = controller.device("demo-tv")
    assert tv is not None
    assert tv.needs_pairing

    pairing.submit_pin("1357")
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
    steps = 1

    async def submit_pin(self, pin: str) -> bool:
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

    assert controller.snapshot()["appearance"] == {
        "theme": "dark",
        "background": "sky",
        "appIcons": True,
    }


async def test_unknown_appearance_is_ignored(
    backend: DemoBackend, caplog: pytest.LogCaptureFixture
) -> None:
    controller = await _started(backend)

    controller.set_appearance("neon", "sky")
    controller.set_appearance("dark", "plaid")
    await controller.runner.drain()

    assert controller.snapshot()["appearance"] == {
        "theme": "system",
        "background": "mist",
        "appIcons": True,
    }
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
    for pin in ("1234", "5678"):
        controller.handle({"type": "submitPin", "pin": pin})
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


# Remote and media controls


async def _paired_tv(controller: AppController) -> None:
    controller.pair("demo-tv")
    await controller.runner.drain()
    for pin in ("1234", "5678"):
        controller.pairing.submit_pin(pin)
        await controller.runner.drain()


async def test_connected_tv_shows_its_controls(backend: DemoBackend) -> None:
    controller = await _started(backend)
    await _paired_tv(controller)  # pairing connects

    tv = next(d for d in controller.snapshot()["devices"] if d["id"] == "demo-tv")
    controls = tv["controls"]
    assert controls["remote"] is True
    assert controls["volume"] == "steps"
    assert controls["canPower"] is True
    assert "play_pause" in controls["media"]
    assert controls["nowPlaying"]["title"] == "A Walk in the Woods"
    assert controls["nowPlaying"]["totalTime"] == 2640.0

    controller.disconnect("demo-tv")
    await controller.runner.drain()
    tv = next(d for d in controller.snapshot()["devices"] if d["id"] == "demo-tv")
    assert tv["controls"] is None


async def test_control_commands_reach_the_backend(backend: DemoBackend) -> None:
    controller = await _started(backend)
    await _paired_tv(controller)

    controller.handle({"type": "press", "id": "demo-tv", "key": "select", "action": "hold"})
    controller.handle({"type": "press", "id": "demo-tv", "key": "menu"})
    controller.handle({"type": "media", "id": "demo-tv", "command": "play_pause"})
    controller.handle({"type": "setPower", "id": "demo-tv", "on": False})
    await controller.runner.drain()

    assert [p[1:] for p in backend.presses] == [
        (RemoteKey.SELECT, KeyAction.HOLD),
        (RemoteKey.MENU, KeyAction.TAP),
    ]
    controls = backend.controls("demo-tv")
    assert controls is not None
    assert controls.power == "off"
    assert controls.now_playing is not None
    assert controls.now_playing.state == "paused"


async def test_volume_slider_sets_the_level(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.connect("demo-speaker-1")
    await controller.runner.drain()

    controller.handle({"type": "setVolume", "id": "demo-speaker-1", "level": 72})
    await controller.runner.drain()

    controls = backend.controls("demo-speaker-1")
    assert controls is not None
    assert controls.volume_level == 72.0


@pytest.mark.parametrize(
    "command",
    [
        {"type": "press", "id": "demo-tv", "key": "jump"},
        {"type": "press", "id": "demo-tv", "key": "up", "action": "wiggle"},
        {"type": "media", "id": "demo-tv", "command": "rewind-forever"},
        {"type": "setVolume", "id": "demo-tv", "level": 101},
        {"type": "setVolume", "id": "demo-tv", "level": True},
        {"type": "setPower", "id": "demo-tv", "on": "yes"},
        {"type": "launchApp", "id": "demo-tv"},
        {"type": "launchApp", "id": "demo-tv", "appId": 7},
        {"type": "setText", "id": "demo-tv", "text": None},
        {"type": "loadApps"},
    ],
)
async def test_malformed_control_commands_are_ignored(
    backend: DemoBackend, command: dict[str, Any]
) -> None:
    controller = await _started(backend)
    controller.handle(command)
    await controller.runner.drain()
    assert backend.presses == []
    assert backend.launched == []
    assert backend.texts == []
    assert controller.snapshot()["devices"][1]["apps"] is None
    assert controller.message is None


async def test_control_errors_show_their_words(backend: DemoBackend) -> None:
    controller = await _started(backend)

    controller.press("demo-speaker-1", RemoteKey.UP)  # not connected
    await controller.runner.drain()
    assert controller.message == {"code": "backend", "text": "This device isn't connected."}

    controller.connect("demo-speaker-1")
    await controller.runner.drain()
    controller.press("demo-speaker-1", RemoteKey.UP)  # a HomePod has no remote pad
    await controller.runner.drain()
    assert controller.message == {"code": "backend", "text": "This device can't do that right now."}


# App launcher and text entry


def _tv(controller: AppController) -> dict[str, Any]:
    return next(d for d in controller.snapshot()["devices"] if d["id"] == "demo-tv")


async def test_launcher_lists_apps_sorted_and_opens_one(backend: DemoBackend) -> None:
    controller = await _started(backend)
    await _paired_tv(controller)
    controls = _tv(controller)["controls"]
    assert (controls["apps"], controls["textEntry"], controls["keyboard"]) == (True, True, False)

    controller.handle({"type": "loadApps", "id": "demo-tv"})
    assert _tv(controller)["apps"] == {"state": "loading", "items": [], "error": None}
    await controller.runner.drain()
    apps = _tv(controller)["apps"]
    assert apps["state"] == "ready"
    names = [app["name"] for app in apps["items"]]
    assert names == sorted(names, key=str.casefold)
    assert {"id": "com.apple.TVSearch", "name": "Search", "icon": None} in apps["items"]

    controller.handle({"type": "launchApp", "id": "demo-tv", "appId": "com.apple.TVSearch"})
    await controller.runner.drain()
    assert backend.launched == [("demo-tv", "com.apple.TVSearch")]
    assert _tv(controller)["controls"]["keyboard"] is True  # Search asks for text

    controller.handle({"type": "press", "id": "demo-tv", "key": "menu"})
    await controller.runner.drain()
    assert _tv(controller)["controls"]["keyboard"] is False


async def test_reloading_keeps_the_list_and_ignores_repeats(backend: DemoBackend) -> None:
    controller = await _started(backend)
    await _paired_tv(controller)
    controller.load_apps("demo-tv")
    await controller.runner.drain()
    calls: list[int] = []
    controller.subscribe(lambda: calls.append(1))

    controller.load_apps("demo-tv")
    controller.load_apps("demo-tv")  # already loading: no second fetch
    apps = _tv(controller)["apps"]
    assert apps["state"] == "loading"
    assert len(apps["items"]) == 10  # the old list stays while it reloads
    await controller.runner.drain()
    assert _tv(controller)["apps"]["state"] == "ready"
    assert len(calls) == 2  # loading, then ready


async def test_apps_on_a_device_without_them_fail_with_words(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.connect("demo-speaker-1")
    await controller.runner.drain()

    controller.load_apps("demo-speaker-1")
    await controller.runner.drain()
    speaker = next(d for d in controller.snapshot()["devices"] if d["id"] == "demo-speaker-1")
    assert speaker["apps"] == {
        "state": "failed",
        "items": [],
        "error": {"code": "backend", "text": "This device can't do that right now."},
    }
    assert controller.message is None  # shown in the launcher, not as a banner


async def test_apps_are_dropped_when_the_device_disconnects(backend: DemoBackend) -> None:
    controller = await _started(backend)
    await _paired_tv(controller)
    controller.load_apps("demo-tv")
    controller.disconnect("demo-tv")  # before the list arrives
    await controller.runner.drain()
    assert _tv(controller)["apps"] is None

    controller.connect("demo-tv")
    controller.load_apps("demo-tv")
    await controller.runner.drain()
    backend.remove("demo-tv")
    assert controller._apps == {}  # pyright: ignore[reportPrivateUsage]


async def test_apps_unexpected_error_logs_only_its_type(
    backend: DemoBackend, caplog: pytest.LogCaptureFixture
) -> None:
    class Broken(DemoBackend):
        async def apps(self, device_id: str) -> list[AppInfo]:
            raise RuntimeError("secret 192.0.2.7")

    broken = Broken(sleep=backend._sleep)  # pyright: ignore[reportPrivateUsage]
    controller = await _started(broken)
    caplog.set_level(logging.ERROR)
    controller.load_apps("demo-tv")
    await controller.runner.drain()
    assert _tv(controller)["apps"]["error"] == {"code": "taskFailed"}
    assert "RuntimeError" in caplog.text
    assert "192.0.2.7" not in caplog.text


async def test_late_apps_result_after_reload_is_ignored(backend: DemoBackend) -> None:
    release = asyncio.Event()

    class Slow(DemoBackend):
        async def apps(self, device_id: str) -> list[AppInfo]:
            await release.wait()
            raise ControlError("This device can't do that right now.")

    slow = Slow(sleep=backend._sleep)  # pyright: ignore[reportPrivateUsage]
    controller = await _started(slow)
    controller.load_apps("demo-tv")
    await asyncio.sleep(0)
    controller._apps.pop("demo-tv")  # pyright: ignore[reportPrivateUsage]
    release.set()
    await controller.runner.drain()
    assert _tv(controller)["apps"] is None


class _SlowText(DemoBackend):
    """Holds each text until the test lets it through."""

    def __init__(self) -> None:
        super().__init__(sleep=_no_wait)
        self.gate = asyncio.Event()

    async def set_text(self, device_id: str, text: str) -> None:
        await self.gate.wait()
        await super().set_text(device_id, text)


async def test_typing_sends_the_newest_text_in_order() -> None:
    backend = _SlowText()
    controller = await _started(backend)
    await _paired_tv(controller)

    for text in ("n", "na", "nat", "natu"):
        controller.handle({"type": "setText", "id": "demo-tv", "text": text})
        await asyncio.sleep(0)
    backend.gate.set()
    await controller.runner.drain()
    assert backend.texts == [("demo-tv", "n"), ("demo-tv", "natu")]


async def test_text_is_capped(backend: DemoBackend) -> None:
    controller = await _started(backend)
    await _paired_tv(controller)
    controller.set_text("demo-tv", "x" * (MAX_TEXT + 50))
    await controller.runner.drain()
    assert backend.texts == [("demo-tv", "x" * MAX_TEXT)]


async def test_text_failure_shows_words_and_typing_recovers(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.set_text("demo-tv", "hello")  # not connected yet
    await controller.runner.drain()
    assert controller.message == {"code": "backend", "text": "This device isn't connected."}

    await _paired_tv(controller)
    controller.set_text("demo-tv", "hello")
    await controller.runner.drain()
    assert backend.texts == [("demo-tv", "hello")]


class _Icons:
    def __init__(self, fail: bool = False) -> None:
        self.asked: list[list[str]] = []
        self.fail = fail
        self.closed = False

    async def icons(self, app_ids: list[str]) -> dict[str, str]:
        self.asked.append(app_ids)
        if self.fail:
            raise OSError("offline")
        return {"com.example.tv": "/app-icons/0123456789abcdef0123456789abcdef.jpg"}

    async def close(self) -> None:
        self.closed = True


async def test_launcher_shows_icons_when_allowed(backend: DemoBackend) -> None:
    icons = _Icons()
    controller = AppController(backend, icons=icons)
    await controller.start()
    await _paired_tv(controller)

    controller.load_apps("demo-tv")
    await controller.runner.drain()
    items = {a["id"]: a for a in _tv(controller)["apps"]["items"]}
    assert items["com.example.tv"]["icon"].startswith("/app-icons/")
    assert items["com.example.music"]["icon"] is None
    assert len(icons.asked[0]) == 10

    controller.handle({"type": "setAppearance", "appIcons": False})  # switched off in Settings
    await controller.runner.drain()
    assert controller.snapshot()["appearance"]["appIcons"] is False
    items = {a["id"]: a for a in _tv(controller)["apps"]["items"]}
    assert items["com.example.tv"]["icon"] is None
    controller.load_apps("demo-tv")
    await controller.runner.drain()
    assert len(icons.asked) == 1  # no lookups while switched off

    controller.handle({"type": "setAppearance", "appIcons": True})
    await controller.runner.drain()
    assert len(icons.asked) == 2
    await controller.stop()
    assert icons.closed


async def test_icon_failures_keep_the_letters(backend: DemoBackend) -> None:
    controller = AppController(backend, icons=_Icons(fail=True))
    await controller.start()
    await _paired_tv(controller)
    controller.load_apps("demo-tv")
    await controller.runner.drain()
    assert _tv(controller)["apps"]["state"] == "ready"
    assert all(a["icon"] is None for a in _tv(controller)["apps"]["items"])
    assert controller.message is None


async def test_malformed_app_icons_choice_is_ignored(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.handle({"type": "setAppearance", "appIcons": "yes"})
    await controller.runner.drain()
    assert controller.appearance.app_icons is True
