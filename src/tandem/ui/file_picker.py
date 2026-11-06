"""The window's file picker for Send to TV, through pywebview's native dialog.

The web page can't see file paths, so the controller asks this picker instead. The window
exists only after the controller is built, so `attach` hands it over later; until then (and
with `--no-window`) there's no window and the picker returns nothing.
"""

from __future__ import annotations

import asyncio
from typing import Any

VIDEO_FILTER = ("Videos (*.mp4;*.m4v;*.mov)", "Audio (*.mp3;*.m4a;*.aac;*.wav)")


class WindowFilePicker:
    def __init__(self) -> None:
        self._window: Any = None

    def attach(self, window: Any) -> None:
        self._window = window

    async def pick_video(self) -> str | None:
        window = self._window
        if window is None:
            return None
        return await asyncio.to_thread(_open_dialog, window)


def _open_dialog(window: Any) -> str | None:  # pragma: no cover - needs a desktop
    import webview  # pyright: ignore[reportMissingTypeStubs]

    wv: Any = webview
    dialog = wv.FileDialog.OPEN if hasattr(wv, "FileDialog") else wv.OPEN_DIALOG
    chosen: Any = window.create_file_dialog(dialog, allow_multiple=False, file_types=VIDEO_FILTER)
    if not chosen:
        return None
    if isinstance(chosen, str):
        return chosen
    items: list[Any] = list(chosen)
    return str(items[0]) if items else None
