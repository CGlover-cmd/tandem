"""The music library's file access (Phase 6): folder walking, tags and artwork via tinytag.

tinytag is pure Python (MIT), so it loads under Smart App Control. Nothing here is logged:
paths, titles and artwork are personal.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from tandem.engine.adapters.decoders import AUDIO_SUFFIXES
from tandem.engine.library import FileEntry, LibraryArt, Tags

COVER_NAMES = ("cover", "folder", "front", "album", "albumart")
COVER_SUFFIXES = (".jpg", ".jpeg", ".png")
MAX_FILES = 50_000
MAX_ART = 8 * 1024 * 1024
_YEAR = re.compile(r"(\d{4})")


def list_files(folder: str) -> tuple[list[FileEntry], set[str]]:
    """Every playable audio file under `folder`, and the folders that hold a cover image."""
    entries: list[FileEntry] = []
    covers: set[str] = set()
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            lower = name.lower()
            if lower.endswith(AUDIO_SUFFIXES):
                path = os.path.join(root, name)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                entries.append(FileEntry(path, stat.st_size, stat.st_mtime))
                if len(entries) >= MAX_FILES:
                    return entries, covers
            elif _is_cover(lower):
                covers.add(str(Path(root)))
    return entries, covers


def read_tags(path: str) -> Tags | None:  # pragma: no cover - needs real audio files
    from tinytag import TinyTag

    tag: Any = TinyTag.get(path, image=True)
    return Tags(
        title=tag.title,
        artist=tag.artist,
        album=tag.album,
        album_artist=tag.albumartist,
        number=_int(tag.track),
        disc=_int(tag.disc),
        year=_year(tag.year),
        duration=float(tag.duration) if tag.duration else None,
        has_art=tag.images.any is not None,
    )


def read_art(path: str) -> LibraryArt | None:
    """Embedded artwork in `path`, else a cover image in its folder."""
    embedded = _embedded_art(path)
    if embedded is not None:
        return embedded
    folder = Path(path).parent
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return None
    for name in names:
        if _is_cover(name.lower()):
            image = folder / name
            try:
                if image.stat().st_size > MAX_ART:
                    continue
                data = image.read_bytes()
            except OSError:
                continue
            mimetype = "image/png" if name.lower().endswith(".png") else "image/jpeg"
            return LibraryArt(data, mimetype)
    return None


def _embedded_art(path: str) -> LibraryArt | None:  # pragma: no cover - needs real audio files
    try:
        from tinytag import TinyTag

        tag: Any = TinyTag.get(path, tags=False, duration=False, image=True)
    except Exception:
        return None
    image: Any = tag.images.any
    if image is None or not image.data or len(image.data) > MAX_ART:
        return None
    mimetype = str(image.mime_type or "image/jpeg")
    if mimetype not in ("image/jpeg", "image/png", "image/gif", "image/bmp", "image/webp"):
        mimetype = "image/jpeg"
    return LibraryArt(bytes(image.data), mimetype)


def _is_cover(lower: str) -> bool:
    stem, _, suffix = lower.rpartition(".")
    return bool(stem) and f".{suffix}" in COVER_SUFFIXES and stem in COVER_NAMES


def _int(value: object) -> int | None:
    try:
        return int(str(value).split("/")[0]) if value not in (None, "") else None
    except ValueError:
        return None


def _year(value: object) -> int | None:
    match = _YEAR.search(str(value or ""))
    return int(match.group(1)) if match else None
