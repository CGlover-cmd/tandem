"""Cast screen in the window and the tray, on the demo backend (invented devices)."""

from __future__ import annotations

from typing import Any

from demo_harness import settle, until

from tandem.bridge import DemoBackend
from tandem.bridge_cast import problem_for
from tandem.engine.screen_cast import CastError, Screen
from tandem.ui.backend import CastQuality, CastState, Problem
from tandem.ui.controller import AppController
from tandem.ui.tray import SEPARATOR, Entry, cast_entries, menu_entries


async def _started(backend: DemoBackend) -> AppController:
    controller = AppController(backend, demo_mode=True)
    await controller.start()
    await settle(controller)
    return controller


async def _paired_tv(controller: AppController) -> None:
    controller.pair("demo-tv")
    await settle(controller)
    for pin in ("1234", "5678"):
        controller.pairing.submit_pin(pin)
        await settle(controller)


def _active(controller: AppController) -> dict[str, Any] | None:
    return controller.snapshot()["cast"]["active"]


def _cast(screen: Any = 1, **extra: Any) -> dict[str, Any]:
    return {"type": "castScreen", "id": "demo-tv", "screen": screen, "quality": "low"} | extra


async def test_screens_are_listed_by_size_only(backend: DemoBackend) -> None:
    controller = await _started(backend)
    assert controller.snapshot()["cast"] == {
        "screens": [
            {"index": 0, "width": 1920, "height": 1080, "primary": True},
            {"index": 1, "width": 2560, "height": 1440, "primary": False},
        ],
        "active": None,
    }
    controller.handle({"type": "loadScreens"})
    controller.handle({"type": "loadScreens"})  # one look at a time
    await settle(controller)
    assert len(controller.cast.screens) == 2


async def test_cast_to_the_tv_then_stop_from_the_tray(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.handle(_cast())
    await settle(controller)
    assert _active(controller) == {
        "deviceId": "demo-tv",
        "state": "failed",
        "problem": {"code": Problem.PAIR_FIRST},
    }
    assert cast_entries(controller) == []

    await _paired_tv(controller)
    controller.handle(_cast(sound=False))
    await until(lambda: controller.cast.casting_to == "demo-tv")
    await until(lambda: (_active(controller) or {}).get("state") == "playing")
    ((device_id, url),) = backend.demo.sent
    assert device_id == "demo-tv"
    assert url.startswith("http://")
    assert url.endswith("/index.m3u8")
    entries = menu_entries(controller)
    assert entries[2:5] == [
        Entry("Casting the screen to Living Room TV", enabled=False),
        Entry("Stop casting", "stop_cast"),
        SEPARATOR,
    ]

    controller.cast.stop()  # the tray's Stop
    await settle(controller)
    assert _active(controller) == {"deviceId": "demo-tv", "state": "ended", "problem": None}
    assert controller.cast.casting_to is None
    assert cast_entries(controller) == []


async def test_bad_cast_commands_are_ignored(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.handle(_cast(screen="main"))
    controller.handle(_cast(quality="ultra"))
    controller.handle(_cast(sound="yes"))
    controller.handle({"type": "castScreen", "screen": 0})
    await settle(controller)
    assert _active(controller) is None


async def test_problems_show_in_the_cast_state(backend: DemoBackend) -> None:
    controller = await _started(backend)
    await backend.cast_screen("demo-gone", 0, CastQuality.STANDARD, True)
    cast = backend.cast()
    assert cast is not None
    assert (cast.state, cast.problem) == (
        CastState.FAILED,
        Problem.SPEAKER_GONE,
    )
    await backend.cast_screen("demo-speaker-2", 0, CastQuality.STANDARD, True)
    await settle(controller)
    cast = backend.cast()
    assert cast is not None
    assert cast.problem == Problem.NOT_A_TV
    assert _active(controller) == {
        "deviceId": "demo-speaker-2",
        "state": "failed",
        "problem": {"code": Problem.NOT_A_TV},
    }


def test_failure_reasons_become_problem_codes() -> None:
    assert problem_for(CastError.ENCODER) == Problem.CAST_FAILED
    assert problem_for(CastError.NO_SCREEN) == Problem.NO_SCREEN
    assert problem_for(CastError.NOT_A_TV) == Problem.NOT_A_TV
    assert problem_for("ConnectionResetError") == Problem.CAST_REFUSED  # the TV's side
    assert problem_for(None) == Problem.CAST_REFUSED


async def test_a_pc_that_cannot_list_screens_offers_none(backend: DemoBackend) -> None:
    def broken() -> list[Screen]:
        raise OSError("no displays")

    backend.demo.screens = broken  # type: ignore[method-assign]
    assert await backend.screens() == []
