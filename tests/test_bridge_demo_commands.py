"""Typed commands in the demo window: the engine's dispatcher on invented demo devices."""

from __future__ import annotations

import asyncio

import pytest

from tandem import bridge
from tandem.ui import backend as ui
from tandem.ui.demo_backend import DemoBackend


async def _no_wait(_seconds: float) -> None:
    await asyncio.sleep(0)


@pytest.fixture
async def demo() -> DemoBackend:
    backend = DemoBackend(sleep=_no_wait)
    backend.commands = bridge.demo_commands(backend)
    await backend.start()
    await backend.connect("demo-speaker-1")  # Patio Speaker: level volume, paused music
    return backend


def _controls(backend: DemoBackend, device_id: str) -> ui.ControlsSnapshot:
    controls = backend.controls(device_id)
    assert controls is not None
    return controls


async def test_demo_play_pause_and_skip(demo: DemoBackend) -> None:
    assert (await demo.run_command("play")).status == "done"
    playing = _controls(demo, "demo-speaker-1").now_playing
    assert playing is not None
    assert playing.state == "playing"

    assert (await demo.run_command("play")).status == "done"  # already playing: no toggle
    assert (await demo.run_command("pause on patio")).status == "done"
    paused = _controls(demo, "demo-speaker-1").now_playing
    assert paused is not None
    assert paused.state == "paused"
    assert (await demo.run_command("next")).code == "next"
    assert (await demo.run_command("previous")).code == "previous"


async def test_demo_volume(demo: DemoBackend) -> None:
    await demo.run_command("volume 70")
    assert _controls(demo, "demo-speaker-1").volume_level == 70.0
    await demo.run_command("louder")
    assert _controls(demo, "demo-speaker-1").volume_level == 80.0
    await demo.run_command("quieter")
    assert _controls(demo, "demo-speaker-1").volume_level == 70.0


async def test_demo_tv_apps_power_and_volume_steps(demo: DemoBackend) -> None:
    pairing = await demo.begin_pairing("demo-tv")
    await pairing.submit_pin("1234")
    await pairing.submit_pin("1234")
    await demo.connect("demo-tv")

    opened = await demo.run_command("open music on the tv")
    assert opened == ui.CommandOutcome(
        "done", "openApp", {"app": "Music", "device": "Living Room TV"}
    )
    assert (await demo.run_command("turn off the tv")).status == "done"
    assert _controls(demo, "demo-tv").power == "off"
    assert (await demo.run_command("volume up on the tv")).status == "done"
    assert demo.presses[-1][1] is ui.RemoteKey.VOLUME_UP
    assert (await demo.run_command("volume 30 on the tv")).code == "noVolumeLevel"


async def test_demo_errors_and_switches(demo: DemoBackend) -> None:
    result = await demo.run_command("pause on office")
    assert result.code == "notConnected"
    assert (await demo.run_command("turn on the lamp")).code == "switchesNotYet"
    services = bridge._DemoServices(demo)  # pyright: ignore[reportPrivateUsage]
    assert services.switches() == ()
    with pytest.raises(bridge.ActionError):
        await services.set_switch("x", True)
    await demo.disconnect("demo-speaker-1")
    with pytest.raises(bridge.ActionError) as failed:
        await services.set_volume("demo-speaker-1", 10)
    assert failed.value.code == "notConnected"


async def test_demo_without_a_command_runner() -> None:
    backend = DemoBackend(sleep=_no_wait)
    assert backend.preview_command("pause").code == "noCommands"
    assert (await backend.run_command("pause")).code == "noCommands"
