"""The window's commands as a table: name → handler, with the field checks they share.

Each panel (devices, pairing, music, audio...) registers its own commands, so a new command is
one entry next to the code it calls, and the field checks (a string, a flag, a number in range)
are written once. Commands arrive from the page as JSON objects with a "type"; anything
missing, malformed or unknown is ignored. `kinds()` lists every name, for the contract test
that keeps `web/src/types.ts` in step (review A5).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import Enum
from typing import Any, TypeVar

E = TypeVar("E", bound=Enum)


class Fields:
    """Typed reads of one command's fields; each returns None when the field is missing or
    the wrong type, so a handler checks once and returns."""

    def __init__(self, command: Mapping[str, Any]) -> None:
        self._command = command

    def has(self, key: str) -> bool:
        return key in self._command

    def text(self, key: str, *, limit: int | None = None) -> str | None:
        value = self._command.get(key)
        if not isinstance(value, str) or (limit is not None and len(value) > limit):
            return None
        return value

    def flag(self, key: str) -> bool | None:
        value = self._command.get(key)
        return value if isinstance(value, bool) else None

    def number(self, key: str, low: float, high: float) -> float | None:
        value = self._command.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return float(value) if low <= value <= high else None

    def integer(self, key: str) -> int | None:
        value = self._command.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def choice(self, kind: type[E], key: str, default: str | None = None) -> E | None:
        try:
            return kind(self._command.get(key, default))
        except ValueError:
            return None

    def texts(self, key: str, *, limit: int) -> list[str] | None:
        value = self._command.get(key)
        if not isinstance(value, list):
            return None
        items: list[object] = value  # pyright: ignore[reportUnknownVariableType]
        if not all(isinstance(item, str) for item in items):
            return None
        return [str(item) for item in items[:limit]]


Handler = Callable[[Fields], None]


class CommandTable:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def on(self, kind: str, handler: Handler) -> None:
        if kind in self._handlers:
            raise ValueError(f"command {kind!r} registered twice")
        self._handlers[kind] = handler

    def on_id(self, kind: str, action: Callable[[str], object]) -> None:
        """A command that needs only an "id" (a device, output or group)."""

        def handler(fields: Fields) -> None:
            item = fields.text("id")
            if item is not None:
                action(item)

        self.on(kind, handler)

    def kinds(self) -> frozenset[str]:
        return frozenset(self._handlers)

    def handle(self, command: Mapping[str, Any]) -> bool:
        """Run `command`. False if its type is unknown (malformed fields are just ignored)."""
        kind = command.get("type")
        handler = self._handlers.get(kind) if isinstance(kind, str) else None
        if handler is None:
            return False
        handler(Fields(command))
        return True
