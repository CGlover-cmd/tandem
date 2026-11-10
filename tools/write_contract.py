"""Write web/src/contract.generated.ts: the window's contract as Python really keeps it.

The page is typed in web/src/types.ts, while Python builds the same JSON by hand
(`AppController.snapshot()`) and accepts commands by name (`AppController.handle`). This writes
what Python sends and accepts into a TypeScript file that `tsc` checks against types.ts:

- a full snapshot of the demo (invented devices) typed as `AppState`, so a field Python adds,
  drops or renames fails the front end's type check;
- every command name Python handles, checked both ways against the `Command` union;
- every problem code Python can send, which a Vitest test checks has words in strings.ts.

Run it after changing either side:  python tools/write_contract.py
tests/ui/test_ui_contract.py fails while the file is out of date.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "web" / "src" / "contract.generated.ts"

# Problem codes the controller sends itself (the rest are tandem.ui.backend.Problem).
CONTROLLER_PROBLEMS = ("pinFormat", "pairingFailed", "taskFailed")


class _Clock:
    """A fixed clock, so the music position in the snapshot never changes."""

    def __call__(self) -> float:
        return 1000.0


async def _no_wait(_seconds: float) -> None:
    await asyncio.sleep(0)


async def _short_waits(seconds: float) -> None:
    await asyncio.sleep(0 if seconds < 20 else seconds)


async def _settle(controller: object) -> None:
    from tandem.ui.controller import AppController

    assert isinstance(controller, AppController)
    for _ in range(3):
        await controller.runner.drain()
        for _ in range(100):
            await asyncio.sleep(0)


async def _pc_muted(controller: object) -> None:
    """Wait, in real time, for the PC's output to show muted: the mute runs on a worker
    thread, which `_settle` can't wait for (ADR-0020)."""
    from tandem.ui.controller import AppController

    assert isinstance(controller, AppController)
    loop = asyncio.get_running_loop()
    end = loop.time() + 5
    while not any(o.state.value == "muted" for o in controller.audio.audio.outputs):
        if loop.time() > end:
            raise RuntimeError("the demo PC never showed muted")
        await asyncio.sleep(0.02)


async def _demo_snapshot() -> tuple[dict[str, object], list[str]]:
    from tandem.bridge import DemoBackend
    from tandem.ui.controller import AppController

    clock = _Clock()
    backend = DemoBackend(sleep=_no_wait, engine_sleep=_short_waits, clock=clock)
    controller = AppController(backend, demo_mode=True, clock=clock)
    await controller.start()
    await _settle(controller)
    # Fill in the nested parts: a connected TV with controls and apps, a playing speaker, a
    # group, a message.
    controller.press("demo-speaker-2", *_tap())  # not connected: sets a message
    controller.pair("demo-tv")
    await _settle(controller)
    controller.pairing.submit_pin("1234")
    await _settle(controller)
    controller.pairing.submit_pin("1234")
    await _settle(controller)
    controller.load_apps("demo-tv")
    controller.handle({"type": "setOutput", "id": "demo-speaker-1", "on": True})
    controller.handle(
        {"type": "saveGroup", "name": "Out Back", "outputs": ["demo-speaker-1", "demo-soundbar"]}
    )
    await _settle(controller)
    await _pc_muted(controller)
    snapshot = controller.snapshot()
    audio = snapshot["audio"]
    assert isinstance(audio, dict)
    for group in audio["groups"]:  # pyright: ignore[reportUnknownVariableType]
        group["id"] = "group:example"  # ids are random: keep the file stable
    kinds = sorted(controller.command_kinds())
    await controller.stop()
    return snapshot, kinds


def _tap() -> tuple[object, object]:
    from tandem.ui.backend import KeyAction, RemoteKey

    return RemoteKey.UP, KeyAction.TAP


def contract_ts() -> str:
    from tandem.ui.backend import Problem

    snapshot, kinds = asyncio.run(_demo_snapshot())
    problems = sorted(
        {v for k, v in vars(Problem).items() if k.isupper()} | set(CONTROLLER_PROBLEMS)
    )
    body = json.dumps(snapshot, indent=2, ensure_ascii=False)
    lines = [
        "// Written by tools/write_contract.py from the Python side; don't edit by hand.",
        "// `tsc` checks it against types.ts, so the two sides can't drift apart silently.",
        'import type { AppState, Command } from "./types";',
        "",
        "/** The demo's whole UI state, as AppController.snapshot() sends it. */",
        f"export const demoSnapshot: AppState = {body};",
        "",
        "/** Every command AppController.handle accepts. */",
        "export const commandTypes = [",
        *(f'  "{kind}",' for kind in kinds),
        '] as const satisfies readonly Command["type"][];',
        "",
        "/** Fails to compile if types.ts has a command Python doesn't handle. */",
        'type Unhandled = Exclude<Command["type"], (typeof commandTypes)[number]>;',
        "export const everyCommandIsHandled: [Unhandled] extends [never] ? true : never = true;",
        "",
        "/** Every problem code Python sends; strings.ts must have words for each. */",
        "export const problemCodes = [",
        *(f'  "{code}",' for code in problems),
        "] as const;",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    OUT.write_text(contract_ts(), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(OUT.parents[2])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
