"""The order the user arranged a device's apps in, kept on this PC.

Tandem can't change the Apple TV's own home screen (pyatv has no way to), so this order is
Tandem's launcher only. Device and app ids are private: the file stays in the UI's data
folder and nothing here is logged.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import cast

from tandem.ui.backend import AppInfo

_LOGGER = logging.getLogger(__name__)

MAX_APPS = 500


class AppOrderStore:
    """Saved app orders by device id. With no `path` it only remembers them in memory."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._orders = _load(path)

    def order(self, device_id: str) -> list[str]:
        return list(self._orders.get(device_id, []))

    def set_order(self, device_id: str, app_ids: list[str]) -> None:
        self._orders[device_id] = list(dict.fromkeys(app_ids))[:MAX_APPS]
        self._save()

    def _save(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp = self._path.with_suffix(".tmp")
            temp.write_text(json.dumps(self._orders), encoding="utf-8")
            os.replace(temp, self._path)
        except OSError as exc:
            _LOGGER.warning("Couldn't save the app order (%s)", type(exc).__name__)


def arrange(apps: list[AppInfo], saved: list[str]) -> list[AppInfo]:
    """Apps in the saved order; apps that are new since then follow, sorted by name."""
    position = {app_id: index for index, app_id in enumerate(saved)}
    known = sorted((a for a in apps if a.id in position), key=lambda a: position[a.id])
    new = sorted((a for a in apps if a.id not in position), key=lambda a: (a.name.casefold(), a.id))
    return known + new


def _load(path: Path | None) -> dict[str, list[str]]:
    if path is None or not path.exists():
        return {}
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _LOGGER.warning("Ignoring an unreadable app order file")
        return {}
    if not isinstance(raw, dict):
        return {}
    orders: dict[str, list[str]] = {}
    for device_id, ids in cast(dict[object, object], raw).items():
        if isinstance(device_id, str) and isinstance(ids, list):
            orders[device_id] = [i for i in cast(list[object], ids) if isinstance(i, str)]
    return orders
