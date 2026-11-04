from __future__ import annotations

import dataclasses

from tandem.ui.backend import LinkState, MusicSnapshot
from tandem.ui.controller import AppController
from tandem.ui.demo_backend import DemoBackend
from tandem.ui.tray import SEPARATOR, Entry, menu_entries, music_entries


async def test_menu_says_when_no_devices_are_found(backend: DemoBackend) -> None:
    entries = menu_entries(AppController(backend))  # not started: no music either

    assert entries == [
        Entry("Open Tandem", "open"),
        SEPARATOR,
        Entry("Looking for devices…", enabled=False),
        SEPARATOR,
        Entry("Quit Tandem", "quit"),
    ]
    assert SEPARATOR.separator
    assert not entries[0].separator


async def test_menu_lists_devices_with_their_state(backend: DemoBackend) -> None:
    controller = AppController(backend)
    await controller.start()
    controller.connect("demo-speaker-1")
    await controller.runner.drain()
    backend._update("demo-soundbar", state=LinkState.CONNECTING)  # pyright: ignore[reportPrivateUsage]

    devices = menu_entries(controller)[2 + len(music_entries(controller)) : -2]

    assert devices == [
        Entry("Den Soundbar", "activate", "demo-soundbar", enabled=False),
        Entry("Living Room TV (pair to use)", "pair", "demo-tv"),
        Entry("Office Speaker", "activate", "demo-speaker-2"),
        Entry("Patio Speaker", "activate", "demo-speaker-1", checked=True),
    ]


async def test_menu_shows_what_the_pc_is_playing(backend: DemoBackend) -> None:
    controller = AppController(backend)
    await controller.start()

    assert menu_entries(controller)[2:6] == [
        Entry("Morning Light · The Example Band", enabled=False),
        Entry("Pause", "music_play_pause"),
        Entry("Next", "music_next"),
        SEPARATOR,
    ]

    assert controller.music is not None
    controller.music = dataclasses.replace(
        controller.music, state="paused", title="A" * 80, commands=frozenset()
    )
    entries = music_entries(controller)
    assert entries[0].label == "A" * 47 + "…"
    assert entries[1:3] == [
        Entry("Play", "music_play_pause", enabled=False),
        Entry("Next", "music_next", enabled=False),
    ]

    controller.music = MusicSnapshot(app="Demo Player")
    assert music_entries(controller)[0].label == "Demo Player"

    backend.stop_music()
    assert music_entries(controller) == []
