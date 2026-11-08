"""Is there a newer Tandem? One look at GitHub's releases list when the window opens.

Off with Advanced settings, "Check for updates". The request goes to api.github.com and sends
nothing about the PC or its devices; GitHub sees the address and the "Tandem" user agent.
Tandem doesn't download or install anything itself: the window links to the release page.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

_LOGGER = logging.getLogger(__name__)

RELEASES_URL = "https://api.github.com/repos/CGlover-cmd/tandem/releases"
RELEASE_PAGE = "https://github.com/CGlover-cmd/tandem/releases/tag/"
_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")

GetJson = Callable[[str, dict[str, str]], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class Update:
    version: str
    url: str


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = _VERSION.fullmatch(text.strip())
    return None if match is None else (int(match[1]), int(match[2]), int(match[3]))


def newest(releases: object, current: str) -> Update | None:
    """The newest published release above `current`, from GitHub's releases list."""
    mine = parse_version(current)
    if mine is None or not isinstance(releases, list):
        return None
    best: tuple[tuple[int, int, int], str] | None = None
    for release in releases:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(release, dict) or release.get("draft"):  # pyright: ignore[reportUnknownMemberType]
            continue
        tag = release.get("tag_name")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        version = parse_version(tag) if isinstance(tag, str) else None
        if version is not None and version > mine and (best is None or version > best[0]):
            best = (version, str(tag))  # pyright: ignore[reportUnknownArgumentType]
    if best is None:
        return None
    number = ".".join(str(part) for part in best[0])
    return Update(number, RELEASE_PAGE + best[1])


async def check(get_json: GetJson, current: str) -> Update | None:
    """Ask GitHub once. None when Tandem is current or GitHub couldn't be reached."""
    try:
        releases = await get_json(RELEASES_URL, {"per_page": "10"})
    except Exception as exc:  # offline, rate-limited, a proxy: try again next launch
        _LOGGER.info("Update check failed (%s)", type(exc).__name__)
        return None
    return newest(releases, current)
