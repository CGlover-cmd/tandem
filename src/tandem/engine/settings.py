"""User settings, stored as JSON and validated field by field.

A bad value in the file falls back to that field's default (with a warning) instead of
discarding everything else, so one hand-edited typo doesn't reset the user's preferences.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from tandem.engine.events import Event, EventBus

_LOGGER = logging.getLogger(__name__)

SETTINGS_VERSION = 1


class Theme(Enum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True, slots=True)
class Settings:
    theme: Theme = Theme.SYSTEM
    start_minimized: bool = False
    launch_at_startup: bool = False
    discovery_interval_s: float = 10.0

    def __post_init__(self) -> None:
        if not 2.0 <= self.discovery_interval_s <= 300.0:
            raise ValueError("discovery_interval_s must be between 2 and 300 seconds")

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {"version": SETTINGS_VERSION}
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            data[field.name] = value.value if isinstance(value, Enum) else value
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Settings:
        """Build settings from parsed JSON. Unknown keys are ignored; bad values use defaults."""
        defaults = cls()
        values: dict[str, Any] = {}
        for field in dataclasses.fields(cls):
            if field.name not in data:
                continue
            default = getattr(defaults, field.name)
            try:
                value = _coerce(data[field.name], default)
                dataclasses.replace(defaults, **{field.name: value})  # runs range checks
            except (TypeError, ValueError):
                _LOGGER.warning("Ignoring invalid setting %r; using the default", field.name)
                continue
            values[field.name] = value
        return cls(**values)


def _coerce(raw: object, default: object) -> object:
    if isinstance(default, Enum):
        return type(default)(raw)
    if isinstance(default, bool):
        if not isinstance(raw, bool):
            raise TypeError("expected true or false")
        return raw
    if isinstance(default, int | float):
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            raise TypeError("expected a number")
        return type(default)(raw)
    if not isinstance(raw, type(default)):
        raise TypeError(f"expected {type(default).__name__}")
    return raw


@dataclass(frozen=True, slots=True)
class SettingsChanged(Event):
    settings: Settings
    previous: Settings


class SettingsStore:
    def __init__(self, path: Path, bus: EventBus | None = None) -> None:
        self._path = path
        self._bus = bus
        self._settings = Settings()

    @property
    def settings(self) -> Settings:
        return self._settings

    def load(self) -> Settings:
        """Read the file. A missing or unreadable file gives defaults (and is left untouched)."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError) as exc:
            _LOGGER.warning("Settings file unreadable (%s); using defaults", type(exc).__name__)
            data = {}
        if not isinstance(data, dict):
            _LOGGER.warning("Settings file has the wrong shape; using defaults")
            data = {}
        self._settings = Settings.from_json(data)  # pyright: ignore[reportUnknownArgumentType]
        return self._settings

    def update(self, **changes: Any) -> Settings:
        """Apply `changes`, save, and publish SettingsChanged. Raises on invalid values."""
        previous = self._settings
        defaults = Settings()
        names = {field.name for field in dataclasses.fields(Settings)}
        coerced: dict[str, Any] = {}
        for name, value in changes.items():
            if name not in names:
                raise TypeError(f"unknown setting {name!r}")
            coerced[name] = _coerce(value, getattr(defaults, name))
        updated = dataclasses.replace(previous, **coerced)
        if updated == previous:
            return previous
        self.save(updated)
        self._settings = updated
        if self._bus is not None:
            self._bus.publish(SettingsChanged(updated, previous))
        return updated

    def save(self, settings: Settings | None = None) -> None:
        """Write atomically, so a crash mid-write never leaves a half-written file."""
        settings = settings or self._settings
        self._path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(settings.to_json(), indent=2) + "\n"
        fd, tmp = tempfile.mkstemp(prefix=".settings-", dir=self._path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp, self._path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
