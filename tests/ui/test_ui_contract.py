"""The window's message contract stays in step with web/src/types.ts (review A5)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "tools" / "write_contract.py"


def test_the_generated_contract_is_up_to_date() -> None:
    spec = importlib.util.spec_from_file_location("write_contract", TOOL)
    assert spec is not None
    assert spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    expected = tool.contract_ts()
    actual = tool.OUT.read_text(encoding="utf-8")
    assert actual == expected, "run: python tools/write_contract.py (then the web type check)"
