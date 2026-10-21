"""Start the Tandem window and tray icon."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import cast

import qasync
from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtQml import QQmlApplicationEngine, QQmlError
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from tandem.ui.demo_backend import DemoBackend
from tandem.ui.platform import add_qt_dll_directory, reduce_motion
from tandem.ui.tray import Tray, app_icon
from tandem.ui.viewmodels import AppViewModel

QML_DIR = Path(__file__).resolve().parent / "qml"

_LOGGER = logging.getLogger(__name__)


def create_engine(vm: QObject) -> QQmlApplicationEngine:
    """Load the main window with `vm` as its `app` property."""
    engine = QQmlApplicationEngine()
    engine.warnings.connect(_log_qml_warnings)
    engine.addImportPath(str(QML_DIR))
    engine.setInitialProperties({"app": vm})
    engine.loadFromModule("Tandem", "Main")
    return engine


def _log_qml_warnings(warnings: list[QQmlError]) -> None:
    for warning in warnings:
        _LOGGER.warning("QML: %s", warning.toString())


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    parser = argparse.ArgumentParser(prog="tandem-ui", description="Tandem's window.")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use invented devices (the only mode until the engine is wired in)",
    )
    parser.add_argument(
        "--screenshot",
        metavar="PNG",
        type=Path,
        help="render the window with demo devices to an image, then exit",
    )
    parser.add_argument(
        "--theme",
        choices=("light", "dark"),
        help="with --screenshot: force light or dark mode",
    )
    parser.add_argument(
        "--pairing", action="store_true", help="with --screenshot: show the pairing sheet"
    )
    args = parser.parse_args(argv[1:])
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    add_qt_dll_directory()
    QApplication.setApplicationName("Tandem")
    QApplication.setOrganizationName("Tandem")
    app = QApplication(argv[:1])
    app.setWindowIcon(app_icon())
    # Quitting goes through our own event so the asyncio loop can shut down cleanly.
    app.setQuitOnLastWindowClosed(False)
    return cast(int, qasync.run(_run(app, args)))


async def _run(app: QApplication, args: argparse.Namespace) -> int:
    screenshot: Path | None = args.screenshot
    if screenshot is not None and args.theme is not None:
        scheme = Qt.ColorScheme.Dark if args.theme == "dark" else Qt.ColorScheme.Light
        QGuiApplication.styleHints().setColorScheme(scheme)
    can_hide = screenshot is None and QSystemTrayIcon.isSystemTrayAvailable()
    backend = DemoBackend()
    vm = AppViewModel(
        backend,
        demo_mode=True,
        reduce_motion=reduce_motion() or screenshot is not None,
        can_hide_to_tray=can_hide,
    )
    engine = create_engine(vm)
    roots = engine.rootObjects()
    if not roots or not isinstance(roots[0], QQuickWindow):
        return 1
    window = roots[0]

    quit_event = asyncio.Event()
    vm.quitRequested.connect(quit_event.set)

    def show_window() -> None:
        window.show()
        if window.visibility() == QWindow.Visibility.Minimized:
            window.showNormal()
        window.raise_()
        window.requestActivate()

    tray = Tray(vm, show_window=show_window, quit_app=quit_event.set) if can_hide else None
    vm.runner.run(vm.start())

    if screenshot is not None:
        await asyncio.sleep(2.0)
        if args.pairing:
            vm.pairDevice("demo-tv")
        await asyncio.sleep(1.5)
        app.processEvents()
        ok = window.grabWindow().save(str(screenshot))
        await vm.stop()
        return 0 if ok else 1

    await quit_event.wait()
    if tray is not None:
        tray.hide()
    window.hide()
    await vm.stop()
    return 0
