"""Each output's volume and delay, kept between runs (Phase 5).

Lining outputs up by ear takes a while, so the result is saved. The file is keyed by output id,
which for an AirPlay device is its device id (private): it lives next to the settings in the
user's own folder and is never put in a diagnostics bundle.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

MAX_OUTPUTS = 200


@dataclass(frozen=True, slots=True)
class OutputPrefs:
    volume: float | None = None
    delay_ms: int = 0
    on: bool = False
    """The user had it on (for "turn my speakers back on" at the next start)."""


class OutputPrefsStore:
    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._prefs: dict[str, OutputPrefs] = {}

    def get(self, output_id: str) -> OutputPrefs:
        return self._prefs.get(output_id, OutputPrefs())

    def were_on(self) -> list[str]:
        """Outputs the user left on."""
        return [output_id for output_id, prefs in self._prefs.items() if prefs.on]

    def load(self) -> None:
        if self._path is None:
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            _LOGGER.warning("Output settings unreadable (%s); starting fresh", type(exc).__name__)
            return
        if not isinstance(data, dict):
            return
        for key, value in list(data.items())[:MAX_OUTPUTS]:  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            volume = value.get("volume")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            delay = value.get("delay_ms", 0)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if volume is not None and not (isinstance(volume, int | float) and 0 <= volume <= 100):
                volume = None
            if isinstance(delay, bool) or not isinstance(delay, int) or not 0 <= delay <= 10_000:
                delay = 0
            self._prefs[key] = OutputPrefs(
                None if volume is None else float(volume),  # pyright: ignore[reportUnknownArgumentType]
                delay,
                value.get("on") is True,  # pyright: ignore[reportUnknownMemberType]
            )

    def update(
        self,
        output_id: str,
        *,
        volume: float | None = None,
        delay_ms: int | None = None,
        on: bool | None = None,
    ) -> OutputPrefs:
        current = self.get(output_id)
        updated = OutputPrefs(
            current.volume if volume is None else volume,
            current.delay_ms if delay_ms is None else delay_ms,
            current.on if on is None else on,
        )
        if updated != current:
            self._prefs[output_id] = updated
            self._save()
        return updated

    def _save(self) -> None:
        if self._path is None:
            return
        data = {
            k: {"volume": v.volume, "delay_ms": v.delay_ms, "on": v.on}
            for k, v in self._prefs.items()
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".outputs-", dir=self._path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
            os.replace(tmp, self._path)
        except OSError as exc:
            _LOGGER.warning("Couldn't save output settings (%s)", type(exc).__name__)
