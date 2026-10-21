from __future__ import annotations

from PySide6.QtWidgets import QApplication

from tandem.ui.demo_backend import DemoBackend
from tandem.ui.tray import Tray, app_icon
from tandem.ui.viewmodels import AppViewModel


def _menu_texts(tray: Tray) -> list[str]:
    return [a.text() for a in tray.menu.actions() if not a.isSeparator()]


def test_icon_has_every_tray_size(qapp: QApplication) -> None:
    sizes = {s.width() for s in app_icon().availableSizes()}
    assert {16, 20, 24, 32}.issubset(sizes)


async def test_menu_lists_devices_and_follows_state(
    qapp: QApplication, backend: DemoBackend
) -> None:
    vm = AppViewModel(backend, can_hide_to_tray=True)
    shown: list[bool] = []
    quit_calls: list[bool] = []
    tray = Tray(
        vm, show_window=lambda: shown.append(True), quit_app=lambda: quit_calls.append(True)
    )
    assert "Looking for devices…" in _menu_texts(tray)

    await vm.start()
    texts = _menu_texts(tray)
    assert texts[0] == "Open Tandem"
    assert "Living Room TV (pair to use)" in texts
    assert "Patio Speaker" in texts
    assert texts[-1] == "Quit Tandem"

    vm.activate("demo-speaker-1")
    await vm.runner.drain()
    menu = tray.menu
    speaker = next(a for a in menu.actions() if a.text() == "Patio Speaker")
    assert speaker.isChecked()

    pair = next(a for a in menu.actions() if a.text().startswith("Living Room TV"))
    pair.trigger()
    assert shown == [True]
    assert vm.pairing_flow.state == "starting"
    tray.hide()
