"""Hardware check (Phase 6): does opening a catalog song link play it in the Apple Music app,
or only show its page? Runs one search for a generic word and opens the first song once.

Prints nothing about the song (title, artist, link): only counts and whether Windows took the
link. Usage: python spikes/apple_music_link.py [word]
"""

from __future__ import annotations

import asyncio
import os
import sys

from tandem.engine.adapters.itunes_catalog import (
    badge_fetcher,
    fetch_image,
    open_in_apple_music,
    search_catalog,
)
from tandem.engine.apple_catalog import AppleCatalog
from tandem.engine.events import EventBus


async def main(word: str) -> None:
    catalog = AppleCatalog(
        EventBus(),
        search_catalog,
        fetch_image,
        open_in_apple_music,
        fetch_badge=badge_fetcher("us"),
    )
    await catalog.search(word)
    status = catalog.status
    print(f"songs: {len(status.songs)}, albums: {len(status.albums)}, error: {status.error}")
    if not status.songs:
        return
    opened = await catalog.open(status.songs[0].id)
    print("handed to Windows:", opened)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "love"))
    sys.stdout.flush()
    os._exit(0)
