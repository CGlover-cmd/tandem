"""The engine's outputs (review A3): saved settings, states and groups, without the window."""

from __future__ import annotations

import pytest

from conftest import FakeBackend, make_device
from tandem.engine.command_dispatch import CommandDispatcher, EngineCommandServices, Outcome
from tandem.engine.events import EventBus
from tandem.engine.models import Service
from tandem.engine.output_groups import GroupStore
from tandem.engine.output_prefs import OutputPrefsStore
from tandem.engine.outputs import (
    OutputError,
    OutputProblem,
    OutputsChanged,
    OutputState,
    classify,
)
from tandem.engine.service import Engine

PATIO = make_device(id="AA:BB:CC:00:00:21", name="Patio Speaker")
LOFT = make_device(id="AA:BB:CC:00:00:22", name="Loft Speaker")
LOCKED = make_device(
    id="AA:BB:CC:00:00:23", name="Shed Speaker", needs_pairing=frozenset({Service.AIRPLAY})
)


async def _engine(**kwargs: object) -> Engine:
    engine = Engine(FakeBackend([PATIO, LOFT, LOCKED]), **kwargs)  # type: ignore[arg-type]
    await engine.scan()
    return engine


def _state(engine: Engine, output_id: str) -> OutputState:
    return next(s for s in engine.outputs.statuses() if s.id == output_id).state


async def test_every_caller_gets_the_saved_volume_and_delay() -> None:
    prefs = OutputPrefsStore(None)
    prefs.update(PATIO.id, volume=25.0, delay_ms=120)
    engine = await _engine(output_prefs=prefs)
    # The command bar starts outputs through the engine, so it gets the saved settings too.
    result = await CommandDispatcher(EngineCommandServices(engine)).run(
        "send audio to patio speaker"
    )
    assert result.outcome is Outcome.DONE, result
    _, volume, delay = engine.outputs_on()[PATIO.id]
    assert (volume, delay) == (25.0, 120)
    assert prefs.get(PATIO.id).on
    await engine.close()


async def test_recent_outputs_and_stop_all_are_remembered() -> None:
    engine = await _engine()
    changes: list[OutputsChanged] = []
    engine.bus.subscribe(OutputsChanged, changes.append)
    await engine.outputs.start(PATIO.id)
    await engine.outputs.start(LOFT.id)
    await engine.outputs.start(PATIO.id)
    assert engine.outputs.recent == [PATIO.id, LOFT.id]
    assert _state(engine, PATIO.id) is OutputState.STREAMING
    await engine.outputs.stop_all()
    assert not engine.outputs_on()
    assert engine.outputs.prefs.were_on() == []
    assert changes  # the window follows along
    await engine.close()


async def test_outputs_that_cannot_play_say_why() -> None:
    engine = await _engine()
    with pytest.raises(OutputError) as gone:
        await engine.outputs.start("AA:BB:CC:00:00:99")
    assert gone.value.reason == OutputError.GONE
    with pytest.raises(OutputError) as locked:
        await engine.outputs.start(LOCKED.id)
    assert locked.value.reason == OutputError.PAIR_FIRST

    async def refuse(output_id: str, **_settings: object) -> None:
        raise TimeoutError

    engine.start_output = refuse  # type: ignore[method-assign]
    with pytest.raises(OutputError) as failed:
        await engine.outputs.start(PATIO.id)
    assert failed.value.reason == OutputError.NO_AUDIO
    status = next(s for s in engine.outputs.statuses() if s.id == PATIO.id)
    assert (status.state, status.problem) == (OutputState.FAILED, OutputProblem.UNREACHABLE)
    await engine.close()


async def test_groups_switch_their_members_and_fail_only_when_none_play() -> None:
    groups = GroupStore(None)
    engine = await _engine(output_groups=groups, bus=EventBus())
    group = engine.outputs.save_group("Out Back", [PATIO.id, LOFT.id])
    await engine.outputs.set_group(group.id, True)
    assert set(engine.outputs_on()) == {PATIO.id, LOFT.id}
    await engine.outputs.set_group(group.id, False)
    assert not engine.outputs_on()

    locked = engine.outputs.save_group("Shed", [LOCKED.id])
    with pytest.raises(OutputError) as none:
        await engine.outputs.set_group(locked.id, True)
    assert none.value.reason == OutputError.GROUP_NONE_PLAYED
    with pytest.raises(OutputError) as bad:
        engine.outputs.save_group("  ", [PATIO.id])
    assert bad.value.reason == OutputError.BAD_GROUP
    with pytest.raises(OutputError) as missing:
        await engine.outputs.set_group("group-nope", True)
    assert missing.value.reason == OutputError.GROUP_GONE
    await engine.close()


def test_failures_are_classified_by_what_went_wrong() -> None:
    assert classify("AuthenticationError", TimeoutError()) is OutputProblem.ACCESS
    assert classify(None, TimeoutError()) is OutputProblem.UNREACHABLE
    assert classify("ProtocolError", ValueError()) is OutputProblem.FAILED
