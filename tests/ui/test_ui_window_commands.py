"""The window's command table (review A6)."""

from __future__ import annotations

import pytest

from tandem.ui.backend import KeyAction
from tandem.ui.window_commands import CommandTable, Fields


def test_fields_return_none_for_missing_or_wrong_values() -> None:
    f = Fields({"id": "x", "on": 1, "level": True, "ms": 50, "names": ["a", 2], "key": "hold"})
    assert f.text("id") == "x"
    assert f.text("id", limit=0) is None
    assert f.flag("on") is None  # 1 is not a bool
    assert f.number("level", 0, 100) is None  # a bool is not a number
    assert f.number("ms", 0, 10) is None  # out of range
    assert f.number("ms", 0, 100) == 50.0
    assert f.integer("ms") == 50
    assert f.texts("names", limit=5) is None
    assert f.choice(KeyAction, "key") is KeyAction.HOLD
    assert f.choice(KeyAction, "missing", "tap") is KeyAction.TAP
    assert f.choice(KeyAction, "id") is None


def test_the_table_runs_known_commands_and_refuses_duplicates() -> None:
    seen: list[str] = []
    table = CommandTable()
    table.on_id("connect", seen.append)
    assert table.handle({"type": "connect", "id": "demo-tv"})
    assert table.handle({"type": "connect", "id": 3})  # known, malformed: ignored
    assert not table.handle({"type": "nope"})
    assert not table.handle({"id": "demo-tv"})
    assert seen == ["demo-tv"]
    assert table.kinds() == {"connect"}
    with pytest.raises(ValueError, match="twice"):
        table.on_id("connect", seen.append)
