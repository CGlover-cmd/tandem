"""The user's own photo as the window background (Settings, Background, "Your photo").

The window shrinks the picture and re-encodes it as a JPEG before sending it, which also drops
its metadata (camera, place). Tandem keeps one copy in its data folder and serves it to the
window only (token-gated, like the artwork). The photo is personal: never logged.
"""

from __future__ import annotations

import os
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
"""Largest photo accepted. The window sends about 0.5 MB (2560 px on the long side)."""

_JPEG_START = b"\xff\xd8\xff"
_JPEG_END = b"\xff\xd9"


def is_jpeg(data: bytes) -> bool:
    return data.startswith(_JPEG_START) and data.rstrip(b"\x00").endswith(_JPEG_END)


class BackgroundPhoto:
    def __init__(self, folder: Path) -> None:
        self.path = folder / "background.jpg"

    @property
    def version(self) -> int | None:
        """Changes whenever the photo does (for the page's cache); None when there's none."""
        try:
            return self.path.stat().st_mtime_ns
        except OSError:
            return None

    def save(self, data: bytes) -> bool:
        """Keep `data` as the photo. False (and nothing changed) if it isn't a JPEG we take."""
        if not 0 < len(data) <= MAX_BYTES or not is_jpeg(data):
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_suffix(".part")
        partial.write_bytes(data)
        os.replace(partial, self.path)
        return True

    def read(self) -> bytes | None:
        try:
            return self.path.read_bytes()
        except OSError:
            return None

    def remove(self) -> None:
        self.path.unlink(missing_ok=True)
