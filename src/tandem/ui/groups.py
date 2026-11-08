"""Speaker groups as the window sees them, shared by the engine bridge and the demo.

A group is a saved set of outputs ("Downstairs") turned on and off together. The engine keeps
the real ones (`tandem.engine.output_groups`); this module only works out a group's state from
its members and switches the members, through the `Backend`'s own output calls.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Protocol

from tandem.ui.backend import (
    AudioError,
    AudioSnapshot,
    GroupSnapshot,
    GroupState,
    OutputSnapshot,
    OutputState,
    Problem,
)

_LIVE = {OutputState.STARTING, OutputState.STREAMING, OutputState.WAITING}


class Group(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def name(self) -> str: ...
    @property
    def outputs(self) -> tuple[str, ...]: ...


class Outputs(Protocol):
    """What turning a group on needs: the outputs and their switches."""

    def audio(self) -> AudioSnapshot: ...
    async def set_output(self, output_id: str, on: bool) -> None: ...


async def set_members(backend: Outputs, members: Sequence[str], on: bool) -> None:
    """Turn a group's members on or off together. Fails only if none of them would play."""
    available = {o.id: o for o in backend.audio().outputs}
    targets = [m for m in members if m in available and not available[m].needs_pairing]
    if not targets:
        raise AudioError(Problem.GROUP_NONE_PLAYED if on else Problem.GROUP_GONE)
    results = await asyncio.gather(
        *(backend.set_output(m, on) for m in targets), return_exceptions=True
    )
    if on and all(isinstance(r, BaseException) for r in results):
        raise AudioError(Problem.GROUP_NONE_PLAYED)


def group_snapshots(
    groups: Sequence[Group], outputs: Sequence[OutputSnapshot]
) -> tuple[GroupSnapshot, ...]:
    by_id = {o.id: o for o in outputs}
    snapshots: list[GroupSnapshot] = []
    for group in groups:
        members = [by_id[m] for m in group.outputs if m in by_id]
        live = [m for m in members if m.state in _LIVE]
        if any(m.state is OutputState.STARTING for m in members):
            state = GroupState.STARTING
        elif members and len(live) == len(members):
            state = GroupState.ON
        elif live:
            state = GroupState.PARTLY
        else:
            state = GroupState.OFF
        snapshots.append(GroupSnapshot(group.id, group.name, group.outputs, state))
    return tuple(snapshots)
