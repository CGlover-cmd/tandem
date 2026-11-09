"""The device cards' Audio, Video and Remote buttons, and the speakers' audio-only remote."""

from __future__ import annotations

from typing import Any

from demo_harness import settle

from tandem.bridge import DemoBackend
from tandem.engine.adapters.demo import PATIO, TV
from tandem.ui.backend import ControlsSnapshot, DeviceKind, LinkState, MediaCommand
from tandem.ui.controller import AppController, _controls_json  # pyright: ignore[reportPrivateUsage]

TV_PINS = ("4821", "1357")  # the demo TV asks for two PINs: remote control, then AirPlay


async def _started(backend: DemoBackend) -> AppController:
    controller = AppController(backend, demo_mode=True)
    await controller.start()
    await settle(controller)
    return controller


def _card(controller: AppController, device_id: str) -> dict[str, Any]:
    return next(d for d in controller.snapshot()["devices"] if d["id"] == device_id)


async def _enter_pins(controller: AppController) -> None:
    await settle(controller)
    for pin in TV_PINS:
        controller.pairing.submit_pin(pin)
        await settle(controller)
    assert controller.pairing.state == "done"


async def test_audio_button_plays_and_stops_a_speaker(backend: DemoBackend) -> None:
    controller = await _started(backend)
    assert _card(controller, PATIO)["audio"] == "off"

    controller.handle({"type": "deviceAudio", "id": PATIO, "on": True})
    await settle(controller)
    assert _card(controller, PATIO)["audio"] == "on"
    assert _card(controller, PATIO)["state"] == "connected"  # turning it on connects it
    output = next(o for o in controller.audio.audio.outputs if o.id == PATIO)
    assert output.state.value == "streaming"  # the same switch as the Audio panel's

    controller.handle({"type": "deviceAudio", "id": PATIO, "on": False})
    await settle(controller)
    assert _card(controller, PATIO)["audio"] == "off"


async def test_audio_on_an_unpaired_tv_pairs_then_plays(backend: DemoBackend) -> None:
    controller = await _started(backend)
    assert _card(controller, TV)["audio"] == "off"

    controller.set_device_audio(TV, True)
    assert controller.pairing.state == "starting"
    await _enter_pins(controller)

    assert _card(controller, TV)["audio"] == "on"


async def test_turning_audio_off_never_opens_pairing(backend: DemoBackend) -> None:
    controller = await _started(backend)

    controller.set_device_audio(TV, False)

    assert controller.pairing.state == "closed"


async def test_video_or_remote_on_an_unpaired_tv_pairs_and_connects(
    backend: DemoBackend,
) -> None:
    controller = await _started(backend)

    controller.handle({"type": "openDevice", "id": TV})
    await _enter_pins(controller)

    device = controller.device(TV)
    assert device is not None
    assert device.state is LinkState.CONNECTED
    assert _card(controller, TV)["audio"] == "off"  # only the Audio button turns sound on


async def test_open_device_connects_a_paired_speaker(backend: DemoBackend) -> None:
    controller = await _started(backend)

    controller.open_device(PATIO)
    await settle(controller)

    device = controller.device(PATIO)
    assert device is not None
    assert device.state is LinkState.CONNECTED


async def test_a_plain_pair_forgets_an_earlier_audio_press(backend: DemoBackend) -> None:
    controller = await _started(backend)
    controller.set_device_audio(TV, True)
    await settle(controller)
    controller.pairing.cancel()

    controller.handle({"type": "pair", "id": TV})
    await _enter_pins(controller)

    assert _card(controller, TV)["audio"] == "off"


async def test_unknown_devices_are_ignored(backend: DemoBackend) -> None:
    controller = await _started(backend)

    controller.set_device_audio("nope", True)
    controller.open_device("nope")
    await settle(controller)

    assert controller.pairing.state == "closed"
    assert controller.device_audio("nope") is None


def test_speakers_get_an_audio_remote_only() -> None:
    everything = ControlsSnapshot(
        remote=True,
        media=frozenset({MediaCommand.PLAY_PAUSE, MediaCommand.NEXT}),
        can_power=True,
        apps=True,
        text_entry=True,
        keyboard=True,
    )

    speaker = _controls_json(everything, DeviceKind.HOMEPOD)
    tv = _controls_json(everything, DeviceKind.APPLE_TV)

    for key in ("remote", "canPower", "apps", "textEntry", "keyboard"):
        assert speaker[key] is False
        assert tv[key] is True
    assert speaker["media"] == tv["media"] == ["next", "play_pause"]
