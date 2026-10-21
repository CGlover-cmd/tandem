from __future__ import annotations

from tandem.ui.backend import LinkState
from tandem.ui.controller import AppController
from tandem.ui.demo_backend import DemoBackend
from tandem.ui.tray import SEPARATOR, Entry, menu_entries


async def test_menu_says_when_no_devices_are_found(backend: DemoBackend) -> None:
    entries = menu_entries(AppController(backend))

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

    devices = menu_entries(controller)[2:-2]

    assert devices == [
        Entry("Den Soundbar", "activate", "demo-soundbar", enabled=False),
        Entry("Living Room TV (pair to use)", "pair", "demo-tv"),
        Entry("Office Speaker", "activate", "demo-speaker-2"),
        Entry("Patio Speaker", "activate", "demo-speaker-1", checked=True),
    ]
