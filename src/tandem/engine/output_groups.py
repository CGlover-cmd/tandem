"""Speaker groups: a named set of outputs ("Downstairs") turned on and off together.

Saved next to the output preferences in the user's own folder. Group names are typed by the
user and can name rooms, so like device names they're shown but never logged; member ids are
device ids (private) and stay in this file only.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

MAX_GROUPS = 50
MAX_NAME = 40
PREFIX = "group:"


@dataclass(frozen=True, slots=True)
class OutputGroup:
    id: str
    name: str
    outputs: tuple[str, ...]


def is_group(output_id: str) -> bool:
    return output_id.startswith(PREFIX)


class GroupStore:
    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._groups: dict[str, OutputGroup] = {}

    def groups(self) -> list[OutputGroup]:
        return sorted(self._groups.values(), key=lambda g: (g.name.casefold(), g.id))

    def get(self, group_id: str) -> OutputGroup | None:
        return self._groups.get(group_id)

    def save(self, name: str, outputs: Sequence[str]) -> OutputGroup:
        """Save a group. A group with the same name (any case) is replaced."""
        name = " ".join(name.split())[:MAX_NAME]
        members = tuple(dict.fromkeys(o for o in outputs if o and not is_group(o)))
        if not name or not members:
            raise ValueError("a group needs a name and at least one output")
        existing = next(
            (g for g in self._groups.values() if g.name.casefold() == name.casefold()), None
        )
        if existing is None and len(self._groups) >= MAX_GROUPS:
            raise ValueError("too many groups")
        group = OutputGroup(
            existing.id if existing else PREFIX + secrets.token_hex(6), name, members
        )
        self._groups[group.id] = group
        self._save()
        return group

    def delete(self, group_id: str) -> bool:
        if self._groups.pop(group_id, None) is None:
            return False
        self._save()
        return True

    def expand(self, ids: Sequence[str]) -> list[str]:
        """Output ids with each group replaced by its members (order kept, no repeats)."""
        out: list[str] = []
        for output_id in ids:
            group = self._groups.get(output_id)
            out.extend(group.outputs if group else (output_id,))
        return list(dict.fromkeys(out))

    def load(self) -> None:
        if self._path is None:
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            _LOGGER.warning("Speaker groups unreadable (%s); starting fresh", type(exc).__name__)
            return
        if not isinstance(data, list):
            return
        for item in data[:MAX_GROUPS]:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(item, dict):
                continue
            group_id, name, outputs = item.get("id"), item.get("name"), item.get("outputs")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if (
                isinstance(group_id, str)
                and is_group(group_id)
                and isinstance(name, str)
                and name.strip()
                and isinstance(outputs, list)
            ):
                members = tuple(o for o in outputs if isinstance(o, str) and o)  # pyright: ignore[reportUnknownVariableType]
                if members:
                    self._groups[group_id] = OutputGroup(group_id, name.strip()[:MAX_NAME], members)

    def _save(self) -> None:
        if self._path is None:
            return
        data = [{"id": g.id, "name": g.name, "outputs": list(g.outputs)} for g in self.groups()]
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".groups-", dir=self._path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
            os.replace(tmp, self._path)
        except OSError as exc:
            _LOGGER.warning("Couldn't save speaker groups (%s)", type(exc).__name__)
