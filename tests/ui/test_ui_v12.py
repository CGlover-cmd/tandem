"""1.2.0 window features: update check, problem reports, Advanced settings, the hotkey."""

from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any

from demo_harness import settle

from tandem.bridge import DemoBackend
from tandem.ui.backend import Appearance
from tandem.ui.controller import AppController, issue_url
from tandem.ui.updates import RELEASE_PAGE, Update, newest, parse_version

RELEASES = [
    {"tag_name": "v1.3.0", "draft": True},  # not published yet: ignored
    {"tag_name": "v1.2.1", "draft": False, "prerelease": True},
    {"tag_name": "v1.2.0", "draft": False},
    {"tag_name": "nightly", "draft": False},  # not a version: ignored
]


def test_newest_release_above_this_one() -> None:
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.2") is None
    assert newest(RELEASES, "1.1.1") == Update("1.2.1", RELEASE_PAGE + "v1.2.1")
    assert newest(RELEASES, "1.2.1") is None
    assert newest({"message": "rate limited"}, "1.0.0") is None
    assert newest(RELEASES, "dev") is None


async def test_the_window_offers_a_newer_version(backend: DemoBackend) -> None:
    asked: list[str] = []
    opened: list[str] = []

    async def get_json(url: str, params: dict[str, str]) -> Any:
        asked.append(url)
        return [{"tag_name": "v99.0.0", "draft": False}]  # newer than any real version

    controller = AppController(backend, get_json=get_json, open_url=opened.append)
    await controller.start()
    await settle(controller)
    update = controller.snapshot()["update"]
    assert update is not None
    assert update["url"].startswith(RELEASE_PAGE)
    controller.handle({"type": "openUpdate"})
    assert opened == [update["url"]]
    assert len(asked) == 1
    await controller.stop()


async def test_no_update_check_when_turned_off(backend: DemoBackend) -> None:
    async def get_json(url: str, params: dict[str, str]) -> Any:
        raise AssertionError("asked GitHub although the check is off")

    await backend.set_appearance(Appearance(update_check=False))
    controller = AppController(backend, get_json=get_json)
    assert controller.snapshot()["appearance"]["updateCheck"] is False
    await controller.start()
    await settle(controller)
    assert controller.snapshot()["update"] is None
    await controller.stop()


async def test_a_failed_update_check_says_nothing(backend: DemoBackend) -> None:
    async def get_json(url: str, params: dict[str, str]) -> Any:
        raise OSError("offline")

    controller = AppController(backend, get_json=get_json)
    await controller.start()
    await settle(controller)
    assert controller.snapshot()["update"] is None
    assert controller.message is None
    await controller.stop()


async def test_report_a_problem(backend: DemoBackend, tmp_path: Path) -> None:
    opened: list[str] = []
    revealed: list[Path] = []
    bundle = tmp_path / "tandem-diagnostics.zip"

    async def write_diagnostics() -> Path | None:
        return bundle

    backend.write_diagnostics = write_diagnostics  # type: ignore[method-assign]
    controller = AppController(backend, open_url=opened.append, reveal=revealed.append)
    controller.handle({"type": "reportProblem"})
    assert controller.snapshot()["reporting"] is True
    await settle(controller)
    assert controller.snapshot()["reporting"] is False
    assert revealed == [bundle]
    assert len(opened) == 1
    assert opened[0].startswith("https://github.com/CGlover-cmd/tandem/issues/new?")


def test_issue_text_has_versions_and_nothing_personal() -> None:
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(issue_url("1.2.0", "10.0.26200")).query)
    body = query["body"][0]
    assert body.startswith("Tandem 1.2.0 on Windows 10.0.26200")
    assert "diagnostics zip" in body


async def test_advanced_settings(backend: DemoBackend) -> None:
    controller = AppController(backend)
    await controller.start()
    for command in (
        {"type": "setAppearance", "restoreOutputs": True, "photoBlur": 12},
        {"type": "setAppearance", "photoBlur": 99},  # out of range: ignored
        {"type": "setAppearance", "photoBlur": "lots"},  # not a number: ignored
        {"type": "setAppearance", "restoreOutputs": "yes"},  # not a switch: ignored
    ):
        controller.handle(command)
        await settle(controller)
    appearance = controller.snapshot()["appearance"]
    assert appearance["restoreOutputs"] is True
    assert appearance["photoBlur"] == 12
    await controller.stop()


async def test_hotkey_asks_the_window_for_commands(backend: DemoBackend) -> None:
    controller = AppController(backend)
    seen = controller.snapshot()["commandsRequested"]
    controller.request_commands()
    assert controller.snapshot()["commandsRequested"] == seen + 1
    controller.set_window_visible(False)
    await settle(controller)
    assert backend._engine.discovery.idle  # pyright: ignore[reportPrivateUsage]


async def test_groups_from_the_window(backend: DemoBackend) -> None:
    controller = AppController(backend)
    await controller.start()
    await settle(controller)
    controller.handle(
        {"type": "saveGroup", "name": "Outside", "outputs": ["demo-speaker-1", "demo-soundbar"]}
    )
    controller.handle({"type": "saveGroup", "name": "Bad", "outputs": "demo-speaker-1"})  # ignored
    await settle(controller)
    (group,) = controller.snapshot()["audio"]["groups"]
    assert (group["name"], group["state"]) == ("Outside", "off")

    controller.handle({"type": "setGroup", "id": group["id"], "on": True})
    await settle(controller)
    assert controller.snapshot()["audio"]["groups"][0]["state"] == "on"
    controller.handle({"type": "setGroup", "id": group["id"], "on": False})
    controller.handle({"type": "deleteGroup", "id": group["id"]})
    await settle(controller)
    assert controller.snapshot()["audio"]["groups"] == []
    await controller.stop()


async def test_line_up_in_the_demo(backend: DemoBackend) -> None:
    controller = AppController(backend)
    await controller.start()
    controller.handle({"type": "lineUp"})
    await settle(controller)
    assert controller.snapshot()["audio"]["lineup"] == {
        "state": "failed",
        "output": None,
        "problem": "tooFew",
    }
    for speaker in ("demo-speaker-1", "demo-speaker-2"):
        controller.handle({"type": "setOutput", "id": speaker, "on": True})
    await settle(controller)
    controller.handle({"type": "lineUp"})
    await settle(controller)
    audio = controller.snapshot()["audio"]
    assert audio["lineup"]["state"] == "done"
    assert sorted(o["delayMs"] for o in audio["outputs"] if o["state"] == "streaming") == [0, 150]
    await controller.stop()
