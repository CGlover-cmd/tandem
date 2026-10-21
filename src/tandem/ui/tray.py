"""System tray icon and quick menu."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from tandem.ui.backend import LinkState
from tandem.ui.viewmodels import AppViewModel


def app_icon() -> QIcon:
    """Two overlapping circles, drawn at runtime so the repo needs no binary icon yet."""
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        radius = size * 0.30
        painter.setBrush(QColor(0, 102, 204))
        painter.drawEllipse(QPointF(size * 0.36, size * 0.5), radius, radius)
        painter.setBrush(QColor(90, 200, 250, 220))
        painter.drawEllipse(QPointF(size * 0.64, size * 0.5), radius, radius)
        painter.setBrush(QColor(255, 255, 255, 120))
        lens = radius * 0.55
        painter.drawEllipse(QRectF(size * 0.5 - lens / 2, size * 0.5 - lens, lens, lens * 2))
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class Tray(QObject):
    def __init__(
        self,
        vm: AppViewModel,
        *,
        show_window: Callable[[], None],
        quit_app: Callable[[], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = vm
        self._show_window = show_window
        self._quit_app = quit_app
        self._told_about_tray = False

        self._menu = QMenu()
        self._icon = QSystemTrayIcon(app_icon(), self)
        self._icon.setToolTip(self.tr("Tandem"))
        self._icon.setContextMenu(self._menu)
        self._icon.activated.connect(self._on_activated)

        model = vm.device_list
        model.rowsInserted.connect(self._rebuild)
        model.rowsRemoved.connect(self._rebuild)
        model.dataChanged.connect(self._rebuild)
        model.modelReset.connect(self._rebuild)
        vm.hiddenToTray.connect(self._on_hidden)

        self._rebuild()
        self._icon.show()

    @property
    def menu(self) -> QMenu:
        return self._menu

    def hide(self) -> None:
        self._icon.hide()

    def _rebuild(self) -> None:
        menu = self._menu
        menu.clear()
        menu.addAction(self.tr("Open Tandem"), self._show_window)
        menu.addSeparator()
        devices = self._vm.device_list.snapshots()
        if not devices:
            searching = menu.addAction(self.tr("Looking for devices…"))
            searching.setEnabled(False)
        for device in devices:
            action = QAction(device.name, menu)
            if device.needs_pairing:
                action.setText(self.tr("%s (pair to use)") % device.name)
                action.triggered.connect(lambda _=False, d=device.id: self._pair(d))
            else:
                action.setCheckable(True)
                action.setChecked(device.state is LinkState.CONNECTED)
                action.setEnabled(device.state is not LinkState.CONNECTING)
                action.triggered.connect(lambda _=False, d=device.id: self._vm.activate(d))
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self.tr("Quit Tandem"), self._quit_app)

    def _pair(self, device_id: str) -> None:
        self._show_window()
        self._vm.pairDevice(device_id)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_window()

    def _on_hidden(self) -> None:
        if self._told_about_tray:
            return
        self._told_about_tray = True
        self._icon.showMessage(
            self.tr("Tandem is still running"),
            self.tr("Open it again from the tray icon. Choose Quit there to close it."),
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )
