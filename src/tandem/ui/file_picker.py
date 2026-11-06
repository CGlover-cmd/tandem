"""The window's file and folder pickers (Send to TV, the music library), through
pywebview's native dialogs.

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

    async def pick_folder(self) -> str | None:
        """A music folder for the library; None if cancelled or there's no window."""
        window = self._window
        if window is None:
            return None
        return await asyncio.to_thread(_folder_dialog, window)


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


def _folder_dialog(window: Any) -> str | None:  # pragma: no cover - needs a desktop
    import webview  # pyright: ignore[reportMissingTypeStubs]

    wv: Any = webview
    dialog = wv.FileDialog.FOLDER if hasattr(wv, "FileDialog") else wv.FOLDER_DIALOG
    chosen: Any = window.create_file_dialog(dialog)
    if not chosen:
        return None
    if isinstance(chosen, str):
        return chosen
    items: list[Any] = list(chosen)
    return str(items[0]) if items else None
