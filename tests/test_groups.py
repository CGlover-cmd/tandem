"""Speaker groups: saving, turning on together, and "send audio to <group>". Invented names."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import FakeBackend, ManualSleep, make_device
from tandem import bridge
from tandem.engine.command_dispatch import CommandDispatcher, EngineCommandServices, Outcome
from tandem.engine.events import EventBus
from tandem.engine.output_groups import GroupStore, is_group
from tandem.engine.service import Engine
from tandem.engine.settings import SettingsStore
from tandem.ui import backend as ui

PATIO = make_device(id="AA:BB:CC:00:00:11", name="Patio Speaker")
LOFT = make_device(id="AA:BB:CC:00:00:12", name="Loft Speaker")


def test_groups_are_saved_replaced_and_expanded(tmp_path: Path) -> None:
    path = tmp_path / "groups.json"
    store = GroupStore(path)
    first = store.save("  Out   Back ", [PATIO.id, PATIO.id, LOFT.id])
    assert first.name == "Out Back"
    assert first.outputs == (PATIO.id, LOFT.id)
    assert is_group(first.id)
    again = store.save("out back", [LOFT.id])  # same name: replaced, same id
    assert again.id == first.id
    assert store.expand([again.id, PATIO.id]) == [LOFT.id, PATIO.id]
    with pytest.raises(ValueError, match="name"):
        store.save("", [PATIO.id])
    with pytest.raises(ValueError, match="name"):
        store.save("Nothing", [])

    reloaded = GroupStore(path)
    reloaded.load()
    assert [g.name for g in reloaded.groups()] == ["out back"]
    assert reloaded.delete(again.id)
    assert not reloaded.delete(again.id)


def test_a_damaged_groups_file_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "groups.json"
    path.write_text("{not json", encoding="utf-8")
    store = GroupStore(path)
    store.load()
    assert store.groups() == []
    path.write_text(
        json.dumps([{"id": "group:a", "name": "Den", "outputs": [PATIO.id]}, {"id": "x"}, 5]),
        encoding="utf-8",
    )
    store.load()
    assert [g.name for g in store.groups()] == ["Den"]


async def test_a_group_turns_on_together(tmp_path: Path, manual_sleep: ManualSleep) -> None:
    bus = EventBus()
    groups = GroupStore(None)
    engine = Engine(FakeBackend([PATIO, LOFT]), bus=bus, sleep=manual_sleep)
    backend = bridge.EngineBackend(
        engine, SettingsStore(tmp_path / "s.json", bus), output_groups=groups
    )
    await backend.start()
    await backend.save_group("Out Back", [PATIO.id, LOFT.id, "gone-speaker"])
    (group,) = backend.audio().groups
    assert group.state is ui.GroupState.OFF
    await backend.set_group(group.id, True)
    assert set(engine.outputs_on()) == {PATIO.id, LOFT.id}
    assert backend.audio().groups[0].state is ui.GroupState.ON
    await backend.set_output(LOFT.id, False)
    assert backend.audio().groups[0].state is ui.GroupState.PARTLY
    await backend.set_group(group.id, False)
    assert not engine.outputs_on()
    with pytest.raises(ui.AudioError):
        await backend.save_group("", [PATIO.id])
    await backend.delete_group(group.id)
    assert backend.audio().groups == ()
    manual_sleep.release()
    await backend.stop()


async def test_send_audio_to_a_group_by_name() -> None:
    engine = Engine(FakeBackend([PATIO, LOFT]))
    await engine.scan()
    groups = GroupStore(None)
    group = groups.save("Out Back", [PATIO.id, LOFT.id])
    services = EngineCommandServices(engine, groups=groups)
    assert group.id in services.audio_targets()
    result = await CommandDispatcher(services).run("send audio to out back")
    assert result.outcome is Outcome.DONE, result
    assert set(engine.outputs_on()) == {PATIO.id, LOFT.id}
    await engine.close()
