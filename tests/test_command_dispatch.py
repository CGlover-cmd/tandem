"""Running typed commands (Phase 9a). Device and app names are invented (docs/PRIVACY.md)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from conftest import FakeBackend, make_device
from tandem.engine import control as ec
from tandem.engine.command_dispatch import (
    Ability,
    ActionError,
    AppChoice,
    Code,
    CommandDispatcher,
    CommandResult,
    EngineCommandServices,
    Outcome,
    SwitchState,
    TargetState,
    abilities,
)
from tandem.engine.commands import MediaAction, SwitchTarget, Target
from tandem.engine.models import DeviceKind, Service
from tandem.engine.service import Engine

TV = Target("tv", "Living Room TV", DeviceKind.APPLE_TV)
LOFT = Target("loft", "Loft Speaker", DeviceKind.HOMEPOD)
PATIO = Target("patio", "Patio Speaker", DeviceKind.HOMEPOD)

SPEAKER_CAN = frozenset(
    {Ability.PLAY, Ability.PAUSE, Ability.NEXT, Ability.PREVIOUS, Ability.VOLUME_LEVEL}
) | {Ability.VOLUME_STEPS}
TV_CAN = frozenset({Ability.PLAY, Ability.PAUSE, Ability.POWER, Ability.APPS, Ability.VOLUME_STEPS})


class FakeServices:
    def __init__(
        self,
        states: Sequence[TargetState] = (),
        switches: Sequence[SwitchState] = (),
        apps: Sequence[AppChoice] = (),
        fail: str | None = None,
    ) -> None:
        self.states = list(states)
        self.switch_states = list(switches)
        self.app_list = list(apps)
        self.fail = fail
        self.calls: list[tuple[Any, ...]] = []

    def targets(self) -> list[TargetState]:
        return self.states

    def switches(self) -> list[SwitchState]:
        return self.switch_states

    async def _record(self, *call: Any) -> None:
        if self.fail is not None:
            raise ActionError(self.fail)
        self.calls.append(call)

    async def media(self, device_id: str, action: MediaAction) -> None:
        await self._record("media", device_id, action)

    async def set_volume(self, device_id: str, level: int) -> None:
        await self._record("set_volume", device_id, level)

    async def volume_step(self, device_id: str, up: bool) -> None:
        await self._record("volume_step", device_id, up)

    async def set_power(self, device_id: str, on: bool) -> None:
        await self._record("set_power", device_id, on)

    async def apps(self, device_id: str) -> list[AppChoice]:
        await self._record("apps", device_id)
        return self.app_list

    async def launch(self, device_id: str, app_id: str) -> None:
        await self._record("launch", device_id, app_id)

    async def set_switch(self, switch_id: str, on: bool) -> None:
        await self._record("set_switch", switch_id, on)


def connected(target: Target, can: frozenset[Ability], *, playing: bool = False) -> TargetState:
    return TargetState(target, connected=True, abilities=can, playing=playing)


def dispatcher(*states: TargetState, **options: Any) -> tuple[CommandDispatcher, FakeServices]:
    services = FakeServices(states, **options)
    return CommandDispatcher(services), services


# Media


async def test_pause_with_one_connected_device() -> None:
    commands, services = dispatcher(connected(LOFT, SPEAKER_CAN), TargetState(PATIO))

    result = await commands.run("pause")

    assert result == CommandResult(Outcome.DONE, Code.PAUSE, {"device": "Loft Speaker"})
    assert services.calls == [("media", "loft", MediaAction.PAUSE)]


async def test_pause_picks_the_one_playing() -> None:
    commands, services = dispatcher(
        connected(LOFT, SPEAKER_CAN), connected(PATIO, SPEAKER_CAN, playing=True)
    )
    await commands.run("pause")
    assert services.calls == [("media", "patio", MediaAction.PAUSE)]


async def test_play_picks_the_one_not_playing() -> None:
    commands, services = dispatcher(
        connected(LOFT, SPEAKER_CAN), connected(PATIO, SPEAKER_CAN, playing=True)
    )
    await commands.run("play")
    assert services.calls == [("media", "loft", MediaAction.PLAY)]


async def test_two_candidates_ask_which_device() -> None:
    commands, services = dispatcher(connected(LOFT, SPEAKER_CAN), connected(PATIO, SPEAKER_CAN))

    result = await commands.run("next")

    assert result.outcome is Outcome.NEEDS_INFO
    assert result.code == Code.WHICH_DEVICE
    assert result.suggestions == ("next on Loft Speaker", "next on Patio Speaker")
    assert services.calls == []


async def test_nothing_connected() -> None:
    commands, _ = dispatcher(TargetState(LOFT))
    assert await commands.run("pause") == CommandResult(Outcome.NOT_AVAILABLE, Code.NO_DEVICE)


async def test_named_device_not_connected() -> None:
    commands, _ = dispatcher(TargetState(LOFT), connected(PATIO, SPEAKER_CAN))
    result = await commands.run("pause on loft")
    assert result == CommandResult(
        Outcome.NOT_AVAILABLE, Code.NOT_CONNECTED, {"device": "Loft Speaker"}
    )


async def test_named_device_that_cant_do_it() -> None:
    commands, _ = dispatcher(connected(TV, TV_CAN))
    result = await commands.run("next on the tv")
    assert result == CommandResult(
        Outcome.NOT_AVAILABLE, Code.CANT_DO_THAT, {"device": "Living Room TV"}
    )


# Volume


async def test_volume_level() -> None:
    commands, services = dispatcher(connected(LOFT, SPEAKER_CAN), connected(TV, TV_CAN))

    result = await commands.run("volume 30")

    assert result == CommandResult(
        Outcome.DONE, Code.VOLUME_SET, {"device": "Loft Speaker", "level": "30"}
    )
    assert services.calls == [("set_volume", "loft", 30)]


async def test_volume_level_on_a_device_with_steps_points_at_volume_up() -> None:
    commands, services = dispatcher(connected(TV, TV_CAN))

    for text in ("volume 30 on the tv", "volume 30"):
        result = await commands.run(text)
        assert result.code == Code.NO_VOLUME_LEVEL, text
        assert result.suggestions == (
            "volume up on Living Room TV",
            "volume down on Living Room TV",
        )
    assert services.calls == []


async def test_volume_on_a_device_without_volume() -> None:
    commands, _ = dispatcher(connected(TV, frozenset({Ability.PLAY})))
    assert (await commands.run("volume 30 on the tv")).code == Code.NO_VOLUME
    assert (await commands.run("volume up on the tv")).code == Code.NO_VOLUME


async def test_volume_level_with_no_device_able() -> None:
    commands, _ = dispatcher(connected(TV, frozenset({Ability.PLAY})), TargetState(LOFT))
    assert (await commands.run("volume 30")).code == Code.NO_DEVICE


async def test_volume_steps() -> None:
    commands, services = dispatcher(connected(TV, TV_CAN))

    up = await commands.run("louder")
    down = await commands.run("volume down")

    assert (up.code, down.code) == (Code.VOLUME_UP, Code.VOLUME_DOWN)
    assert services.calls == [("volume_step", "tv", True), ("volume_step", "tv", False)]


# Apps


async def test_open_an_app_on_the_only_tv() -> None:
    apps = [
        AppChoice("com.example.music", "Music"),
        AppChoice("com.example.video", "Example Video"),
    ]
    commands, services = dispatcher(connected(TV, TV_CAN), connected(LOFT, SPEAKER_CAN), apps=apps)

    preview = commands.preview("open video")
    result = await commands.run("open video")

    assert preview == CommandResult(
        Outcome.READY, Code.OPEN_APP, {"app": "video", "device": "Living Room TV"}
    )
    assert result == CommandResult(
        Outcome.DONE, Code.OPEN_APP, {"app": "Example Video", "device": "Living Room TV"}
    )
    assert services.calls[-1] == ("launch", "tv", "com.example.video")


async def test_an_unknown_app_lists_some_that_exist() -> None:
    apps = [
        AppChoice(f"id.{n}", n) for n in ("Photos", "Music", "TV", "Podcasts", "Arcade", "Maps")
    ]
    commands, services = dispatcher(connected(TV, TV_CAN), apps=apps)

    result = await commands.run("open zzz")

    assert result.outcome is Outcome.NEEDS_INFO
    assert result.code == Code.UNKNOWN_APP
    assert len(result.suggestions) == 5
    assert result.suggestions[0] == "open Arcade on Living Room TV"
    assert all(call[0] != "launch" for call in services.calls)


async def test_a_misspelt_app_suggests_the_close_one() -> None:
    apps = [AppChoice("id.photos", "Photos"), AppChoice("id.music", "Music")]
    commands, _ = dispatcher(connected(TV, TV_CAN), apps=apps)
    result = await commands.run("open musik")
    assert result.code == Code.OPEN_APP  # a near-miss spelling still matches
    result = await commands.run("open xylophone")
    assert result.code == Code.UNKNOWN_APP


# Power and switches


async def test_turn_off_the_tv() -> None:
    commands, services = dispatcher(connected(TV, TV_CAN))
    result = await commands.run("turn off the tv")
    assert result == CommandResult(Outcome.DONE, Code.POWER_OFF, {"device": "Living Room TV"})
    assert services.calls == [("set_power", "tv", False)]


async def test_turn_on_a_switch() -> None:
    switch = SwitchTarget("music", "Tandem music")
    commands, services = dispatcher(switches=[SwitchState(switch)])
    result = await commands.run("turn on tandem music")
    assert result == CommandResult(Outcome.DONE, Code.SWITCH_ON, {"switch": "Tandem music"})
    assert services.calls == [("set_switch", "music", True)]


async def test_switches_before_the_home_bridge() -> None:
    commands, _ = dispatcher(connected(TV, TV_CAN))
    result = await commands.run("turn on the lamp")
    assert result.outcome is Outcome.NOT_AVAILABLE
    assert result.code == Code.SWITCHES_NOT_YET


async def test_unknown_switch_when_there_are_switches() -> None:
    switch = SwitchTarget("music", "Tandem music")
    commands, _ = dispatcher(switches=[SwitchState(switch)])
    result = await commands.run("turn on the lamp")
    assert result.outcome is Outcome.NEEDS_INFO
    assert result.code == Code.UNKNOWN_SWITCH


# Audio, help and problems


@pytest.mark.parametrize("text", ["send audio to loft", "stop streaming", "start streaming"])
async def test_audio_streaming_is_not_available_yet(text: str) -> None:
    commands, _ = dispatcher(connected(LOFT, SPEAKER_CAN))
    result = await commands.run(text)
    assert result == CommandResult(Outcome.NOT_AVAILABLE, Code.AUDIO_NOT_YET)


async def test_help_and_empty_text_list_examples() -> None:
    commands, _ = dispatcher(connected(LOFT, SPEAKER_CAN))
    for text in ("help", ""):
        result = commands.preview(text)
        assert result.outcome is Outcome.HELP
        assert "volume 30 on Loft Speaker" in result.suggestions


async def test_problems_from_the_parser() -> None:
    commands, _ = dispatcher(connected(LOFT, SPEAKER_CAN))
    garbled = await commands.run("blorp")
    unknown = await commands.run("pause on garden")
    loud = await commands.run("volume 300")
    assert (garbled.outcome, garbled.code) == (Outcome.NOT_UNDERSTOOD, "notUnderstood")
    assert (unknown.outcome, unknown.code) == (Outcome.NEEDS_INFO, "unknownDevice")
    assert unknown.params == {"name": "garden"}
    assert (loud.outcome, loud.code) == (Outcome.NOT_UNDERSTOOD, "badVolume")


async def test_preview_touches_nothing() -> None:
    commands, services = dispatcher(connected(LOFT, SPEAKER_CAN))
    result = commands.preview("volume 30")
    assert result.outcome is Outcome.READY
    assert services.calls == []


@pytest.mark.parametrize(
    ("code", "outcome"),
    [
        (Code.NO_RESPONSE, Outcome.FAILED),
        (Code.NOT_CONNECTED, Outcome.NOT_AVAILABLE),
        (Code.CANT_DO_THAT, Outcome.NOT_AVAILABLE),
    ],
)
async def test_a_failing_step(code: str, outcome: Outcome) -> None:
    commands, _ = dispatcher(connected(LOFT, SPEAKER_CAN), fail=code)
    result = await commands.run("pause")
    assert result == CommandResult(outcome, code, {"device": "Loft Speaker"})


# On the real engine, with the fake protocol backend

ENGINE_TV = make_device(
    id="AA:BB:CC:00:00:02",
    name="Living Room TV",
    kind=DeviceKind.APPLE_TV,
    model="Apple TV 4K",
    services=frozenset({Service.AIRPLAY, Service.COMPANION}),
)
ENGINE_SPEAKER = make_device()  # "Living Room Speaker"


@pytest.fixture
async def engine() -> AsyncIterator[tuple[Engine, FakeBackend]]:
    fake = FakeBackend([ENGINE_TV, ENGINE_SPEAKER])
    engine = Engine(fake, discovery_interval=60.0)
    await engine.open()
    await engine.scan()
    yield engine, fake
    await engine.close()


async def _connect(engine: Engine, device_id: str) -> None:
    await engine.connect(device_id, timeout=1)
    for _ in range(20):
        await asyncio.sleep(0)


async def test_engine_services_list_devices(engine: tuple[Engine, FakeBackend]) -> None:
    eng, _ = engine
    services = EngineCommandServices(eng)

    before = services.targets()
    await _connect(eng, ENGINE_TV.id)
    after = {s.target.name: s for s in services.targets()}

    assert [s.connected for s in before] == [False, False]
    assert after["Living Room TV"].connected
    assert Ability.APPS in after["Living Room TV"].abilities
    assert not after["Living Room Speaker"].connected
    assert services.switches() == []


async def test_engine_runs_commands(engine: tuple[Engine, FakeBackend]) -> None:
    eng, fake = engine
    commands = CommandDispatcher(EngineCommandServices(eng))
    await _connect(eng, ENGINE_TV.id)
    controller = fake.controllers[ENGINE_TV.id]

    results = [
        await commands.run(text)
        for text in (
            "pause on the tv",
            "next",
            "volume 25 on the tv",
            "louder",
            "quieter",
            "turn off the tv",
            "open example on the tv",
        )
    ]

    assert [r.outcome for r in results] == [Outcome.DONE] * 7
    assert controller.calls == [
        ("media", ec.MediaCommand.PAUSE),
        ("media", ec.MediaCommand.NEXT),
        ("set_volume", 25.0),
        ("volume_step", True),
        ("volume_step", False),
        ("set_power", False),
        ("apps",),
        ("launch", "com.example.video"),
    ]
    assert results[-1].params == {"app": "Example Video", "device": "Living Room TV"}


async def test_engine_play_pause_toggle_only(engine: tuple[Engine, FakeBackend]) -> None:
    """An app that offers only the play/pause toggle: don't toggle into the wrong state."""
    eng, fake = engine
    fake.controller_options = {
        "capabilities": frozenset({ec.Capability.PLAY_PAUSE, ec.Capability.NOW_PLAYING}),
        "now_playing": ec.NowPlaying(state=ec.PlayState.PAUSED),
    }
    commands = CommandDispatcher(EngineCommandServices(eng))
    await _connect(eng, ENGINE_TV.id)
    controller = fake.controllers[ENGINE_TV.id]

    assert (await commands.run("pause")).outcome is Outcome.DONE
    assert controller.calls == []  # already paused
    assert (await commands.run("play")).outcome is Outcome.DONE
    assert controller.calls == [("media", ec.MediaCommand.PLAY_PAUSE)]


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ec.NotConnectedError(), Code.NOT_CONNECTED),
        (ec.UnsupportedError("pause"), Code.CANT_DO_THAT),
        (ec.ControlError("timed out"), Code.NO_RESPONSE),
    ],
)
async def test_engine_errors_become_codes(
    engine: tuple[Engine, FakeBackend], error: ec.ControlError, code: str
) -> None:
    eng, fake = engine
    commands = CommandDispatcher(EngineCommandServices(eng))
    await _connect(eng, ENGINE_TV.id)
    fake.controllers[ENGINE_TV.id].fail = error

    assert (await commands.run("pause on the tv")).code == code
    assert (await commands.run("open example on the tv")).code == code


async def test_engine_unexpected_errors_are_not_hidden(engine: tuple[Engine, FakeBackend]) -> None:
    eng, fake = engine
    commands = CommandDispatcher(EngineCommandServices(eng))
    await _connect(eng, ENGINE_TV.id)
    fake.controllers[ENGINE_TV.id].fail = KeyError("bug")  # type: ignore[assignment]

    with pytest.raises(KeyError):
        await commands.run("pause on the tv")


async def test_engine_switches_are_off_until_the_bridge(engine: tuple[Engine, FakeBackend]) -> None:
    eng, _ = engine
    with pytest.raises(ActionError):
        await EngineCommandServices(eng).set_switch("music", True)


def test_abilities_from_controls() -> None:
    status = ec.ControlStatus(
        capabilities=frozenset({ec.Capability.PLAY, ec.Capability.NEXT}),
        volume_control=ec.VolumeControl.STEPS,
    )
    assert abilities(status) == {Ability.PLAY, Ability.NEXT, Ability.VOLUME_STEPS}
    level = ec.ControlStatus(volume_control=ec.VolumeControl.LEVEL)
    assert abilities(level) == {Ability.VOLUME_LEVEL, Ability.VOLUME_STEPS}
