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

from tandem.ui.audio_panel import LIVE
from tandem.ui.backend import DeviceKind, LinkState, MusicCommand, OutputState
from tandem.ui.controller import AppController


@dataclass(frozen=True, slots=True)
class Entry:
    label: str = ""
    action: str = ""
    """"open", "activate", "pair", "output", "report", "quit", "music_play_pause" or
    "music_next"; "" for a separator or a note."""
    device_id: str = ""
    checked: bool = False
    enabled: bool = True

    @property
    def separator(self) -> bool:
        return not self.label


SEPARATOR = Entry()

_LABEL_MAX = 48  # longer now-playing lines are cut, so the menu stays narrow


def _now_playing_label(title: str | None, artist: str | None, app: str | None) -> str:
    label = " · ".join(part for part in (title, artist) if part) or app or "Something"
    return label if len(label) <= _LABEL_MAX else label[: _LABEL_MAX - 1].rstrip() + "…"


def music_entries(controller: AppController) -> list[Entry]:
    """What the PC is playing, with play/pause and next (Phase 6). Empty when nothing plays."""
    music = controller.music
    if music is None:
        return []
    playing = music.state == "playing"
    return [
        Entry(_now_playing_label(music.title, music.artist, music.app), enabled=False),
        Entry(
            "Pause" if playing else "Play",
            "music_play_pause",
            enabled=MusicCommand.PLAY_PAUSE in music.commands,
        ),
        Entry("Next", "music_next", enabled=MusicCommand.NEXT in music.commands),
        SEPARATOR,
    ]


def menu_entries(controller: AppController) -> list[Entry]:
    entries = [Entry("Open Tandem", "open"), SEPARATOR, *music_entries(controller)]
    devices = controller.devices()
    if not devices:
        entries.append(Entry("Looking for devices…", enabled=False))
    entries += output_entries(controller)
    for device in devices:
        if device.kind is not DeviceKind.APPLE_TV:
            continue  # speakers are switched on and off above
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
    entries += [
        SEPARATOR,
        Entry("Report a problem…", "report", enabled=not controller.reporting),
        Entry("Quit Tandem", "quit"),
    ]
    return entries


def output_entries(controller: AppController) -> list[Entry]:
    """A switch per speaker or PC output: ticked while Tandem plays there."""
    outputs = [
        o
        for o in controller.audio.audio.outputs
        if not o.needs_pairing and o.state is not OutputState.DIRECT
    ]
    if not outputs:
        return []
    entries = [Entry("Play the PC's sound on", enabled=False)]
    for output in outputs:
        live = output.state in LIVE
        entries.append(
            Entry(
                f"    {output.name}",
                "output",
                output.id,
                checked=live,
                enabled=output.state is not OutputState.STARTING,
            )
        )
    return [*entries, SEPARATOR]


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
            elif entry.action == "output":
                on = not entry.checked
                self._loop.call_soon_threadsafe(
                    self._controller.handle, {"type": "setOutput", "id": entry.device_id, "on": on}
                )
            elif entry.action == "report":
                self._loop.call_soon_threadsafe(self._controller.report_problem)
            elif entry.action == "activate":
                self._loop.call_soon_threadsafe(self._controller.activate, entry.device_id)
            elif entry.action == "music_play_pause":
                self._loop.call_soon_threadsafe(
                    self._controller.music_command, MusicCommand.PLAY_PAUSE
                )
            elif entry.action == "music_next":
                self._loop.call_soon_threadsafe(self._controller.music_command, MusicCommand.NEXT)

        return run


def _constant(value: bool) -> Callable[[object], bool]:
    return lambda _item: value
