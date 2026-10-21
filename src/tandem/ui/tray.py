"""System tray icon and quick menu.

`menu_entries` decides what the menu shows (tested); `Tray` draws it with pystray, which runs
its own thread. Menu clicks are handed back to the asyncio loop thread, where the controller
lives.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tandem.ui.backend import LinkState
from tandem.ui.controller import AppController


@dataclass(frozen=True, slots=True)
class Entry:
    label: str = ""
    action: str = ""  # "open", "activate", "pair", "quit"; "" for a separator or a note
    device_id: str = ""
    checked: bool = False
    enabled: bool = True

    @property
    def separator(self) -> bool:
        return not self.label


SEPARATOR = Entry()


def menu_entries(controller: AppController) -> list[Entry]:
    entries = [Entry("Open Tandem", "open"), SEPARATOR]
    devices = controller.devices()
    if not devices:
        entries.append(Entry("Looking for devices…", enabled=False))
    for device in devices:
        if device.needs_pairing:
            entries.append(Entry(f"{device.name} (pair to use)", "pair", device.id))
        else:
            entries.append(
                Entry(
                    device.name,
                    "activate",
                    device.id,
                    checked=device.state is LinkState.CONNECTED,
                    enabled=device.state is not LinkState.CONNECTING,
                )
            )
    entries += [SEPARATOR, Entry("Quit Tandem", "quit")]
    return entries


class Tray:  # pragma: no cover - needs a desktop; checked by hand
    def __init__(
        self,
        controller: AppController,
        loop: asyncio.AbstractEventLoop,
        *,
        show_window: Callable[[], None],
        quit_app: Callable[[], None],
    ) -> None:
        import pystray  # pyright: ignore[reportMissingTypeStubs]

        from tandem.ui.icon import draw_icon

        self._pystray: Any = pystray
        self._controller = controller
        self._loop = loop
        self._show_window = show_window
        self._quit_app = quit_app
        self._told_about_tray = False
        self._entries = menu_entries(controller)
        self._icon: Any = self._pystray.Icon(
            "Tandem", draw_icon(64), "Tandem", menu=self._pystray.Menu(self._items)
        )
        controller.subscribe(self._on_change)

    def start(self) -> None:
        self._icon.run_detached()

    def stop(self) -> None:
        self._icon.stop()

    def told_hidden(self) -> None:
        """The window was closed to the tray: say so, once."""
        if self._told_about_tray:
            return
        self._told_about_tray = True
        self._icon.notify(
            "Open it again from the tray icon. Choose Quit there to close it.",
            "Tandem is still running",
        )

    # Internals

    def _on_change(self) -> None:  # asyncio loop thread
        entries = menu_entries(self._controller)
        if entries != self._entries:
            self._entries = entries
            self._icon.update_menu()

    def _items(self) -> list[Any]:  # pystray thread
        menu = self._pystray.Menu
        item = self._pystray.MenuItem
        items: list[Any] = []
        for entry in self._entries:
            if entry.separator:
                items.append(menu.SEPARATOR)
                continue
            items.append(
                item(
                    entry.label,
                    self._handler(entry),
                    checked=_constant(entry.checked) if entry.action == "activate" else None,
                    enabled=entry.enabled and bool(entry.action),
                    default=entry.action == "open",
                )
            )
        return items

    def _handler(self, entry: Entry) -> Callable[[], None]:
        def run() -> None:
            if entry.action == "open":
                self._show_window()
            elif entry.action == "quit":
                self._quit_app()
            elif entry.action == "pair":
                self._show_window()
                self._loop.call_soon_threadsafe(self._controller.pair, entry.device_id)
            elif entry.action == "activate":
                self._loop.call_soon_threadsafe(self._controller.activate, entry.device_id)

        return run


def _constant(value: bool) -> Callable[[object], bool]:
    return lambda _item: value
