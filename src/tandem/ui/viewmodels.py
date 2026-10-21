"""ViewModels: plain Python objects between QML and the backend (ADR-0002).

They hold all UI state and logic, so they can be unit-tested without rendering anything.
QML only binds to their properties and calls their slots.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Coroutine
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from tandem.ui.backend import (
    Backend,
    BackendEvent,
    DeviceRemoved,
    DeviceSnapshot,
    DeviceUpdated,
    DiscoveryChanged,
    LinkState,
    PairingError,
    PairingFlow,
    WrongPinError,
)

_LOGGER = logging.getLogger(__name__)

_PIN = re.compile(r"\d{4}")

AnyIndex = QModelIndex | QPersistentModelIndex


class TaskRunner:
    """Run coroutines from Qt slots on the asyncio loop, keep them alive, report failures."""

    def __init__(self, on_error: Callable[[BaseException], None]) -> None:
        self._on_error = on_error
        self._tasks: set[asyncio.Task[None]] = set()

    def run(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = asyncio.get_event_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._done)
        return task

    def _done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self._on_error(error)

    async def drain(self) -> None:
        """Wait for every running task (used by tests and at shutdown)."""
        while self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


class DeviceListModel(QAbstractListModel):
    """The device grid's rows, sorted by name."""

    IdRole = Qt.ItemDataRole.UserRole + 1
    NameRole = Qt.ItemDataRole.UserRole + 2
    KindRole = Qt.ItemDataRole.UserRole + 3
    StateRole = Qt.ItemDataRole.UserRole + 4
    NeedsPairingRole = Qt.ItemDataRole.UserRole + 5
    RetryInRole = Qt.ItemDataRole.UserRole + 6

    countChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[DeviceSnapshot] = []

    # Qt model API

    def rowCount(self, parent: AnyIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: AnyIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        device = self._rows[index.row()]
        if role in (self.NameRole, Qt.ItemDataRole.DisplayRole):
            return device.name
        if role == self.IdRole:
            return device.id
        if role == self.KindRole:
            return device.kind.value
        if role == self.StateRole:
            return device.state.value
        if role == self.NeedsPairingRole:
            return device.needs_pairing
        if role == self.RetryInRole:
            return device.retry_in if device.retry_in is not None else -1.0
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.IdRole: QByteArray(b"deviceId"),
            self.NameRole: QByteArray(b"name"),
            self.KindRole: QByteArray(b"kind"),
            self.StateRole: QByteArray(b"linkState"),
            self.NeedsPairingRole: QByteArray(b"needsPairing"),
            self.RetryInRole: QByteArray(b"retryIn"),
        }

    def _get_count(self) -> int:
        return len(self._rows)

    count = Property(int, _get_count, notify=countChanged)

    # Python API

    def snapshot(self, device_id: str) -> DeviceSnapshot | None:
        row = self._row_of(device_id)
        return None if row is None else self._rows[row]

    def snapshots(self) -> list[DeviceSnapshot]:
        return list(self._rows)

    def upsert(self, device: DeviceSnapshot) -> None:
        row = self._row_of(device.id)
        if row is not None and self._rows[row].name == device.name:
            self._rows[row] = device
            index = self.index(row)
            self.dataChanged.emit(index, index)
            return
        if row is not None:  # renamed: move to its new sorted place
            self.remove(device.id)
        row = self._insert_row(device)
        self.beginInsertRows(QModelIndex(), row, row)
        self._rows.insert(row, device)
        self.endInsertRows()
        self.countChanged.emit()

    def remove(self, device_id: str) -> None:
        row = self._row_of(device_id)
        if row is None:
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._rows[row]
        self.endRemoveRows()
        self.countChanged.emit()

    def _row_of(self, device_id: str) -> int | None:
        for row, device in enumerate(self._rows):
            if device.id == device_id:
                return row
        return None

    def _insert_row(self, device: DeviceSnapshot) -> int:
        key = _sort_key(device)
        for row, other in enumerate(self._rows):
            if key < _sort_key(other):
                return row
        return len(self._rows)


def _sort_key(device: DeviceSnapshot) -> tuple[str, str]:
    return (device.name.casefold(), device.id)


class PairingViewModel(QObject):
    """The PIN pairing sheet.

    States: closed → starting → enterPin ⇄ checking → done; any → failed; cancel → closed.
    """

    stateChanged = Signal()
    deviceNameChanged = Signal()
    errorChanged = Signal()
    paired = Signal(str)  # device id

    def __init__(self, backend: Backend, runner: TaskRunner, parent: QObject | None = None):
        super().__init__(parent)
        self._backend = backend
        self._runner = runner
        self._state = "closed"
        self._device_id = ""
        self._device_name = ""
        self._error = ""
        self._flow: PairingFlow | None = None
        self._attempt = 0  # ignores results from an attempt the user has cancelled

    def _get_state(self) -> str:
        return self._state

    def _get_device_name(self) -> str:
        return self._device_name

    def _get_error(self) -> str:
        return self._error

    state = Property(str, _get_state, notify=stateChanged)
    deviceName = Property(str, _get_device_name, notify=deviceNameChanged)
    error = Property(str, _get_error, notify=errorChanged)

    @property
    def device_id(self) -> str:
        return self._device_id

    def open(self, device_id: str, device_name: str) -> None:
        if self._state != "closed":
            return
        self._attempt += 1
        self._device_id = device_id
        self._device_name = device_name
        self.deviceNameChanged.emit()
        self._set_error("")
        self._set_state("starting")
        self._runner.run(self._begin(self._attempt))

    @Slot(str)
    def submitPin(self, pin: str) -> None:
        if self._state != "enterPin" or self._flow is None:
            return
        pin = pin.strip()
        if not _PIN.fullmatch(pin):
            self._set_error(self.tr("Enter the 4-digit PIN shown on the TV."))
            return
        self._set_error("")
        self._set_state("checking")
        self._runner.run(self._submit(self._attempt, self._flow, pin))

    @Slot()
    def cancel(self) -> None:
        flow = self._flow
        if flow is not None and self._state in ("enterPin", "checking"):
            self._runner.run(flow.cancel())
        self.close()

    @Slot()
    def close(self) -> None:
        self._attempt += 1
        self._flow = None
        self._set_error("")
        self._set_state("closed")

    async def _begin(self, attempt: int) -> None:
        try:
            flow = await self._backend.begin_pairing(self._device_id)
        except PairingError as error:
            if attempt == self._attempt:
                self._fail(str(error))
            return
        if attempt != self._attempt:
            await flow.cancel()
            return
        self._flow = flow
        self._set_state("enterPin")

    async def _submit(self, attempt: int, flow: PairingFlow, pin: str) -> None:
        try:
            await flow.submit_pin(pin)
        except WrongPinError:
            if attempt == self._attempt:
                self._set_error(self.tr("That PIN didn't match. Check the TV and try again."))
                self._set_state("enterPin")
            return
        except PairingError as error:
            if attempt == self._attempt:
                self._fail(str(error))
            return
        if attempt != self._attempt:
            return
        self._flow = None
        self._set_state("done")
        self.paired.emit(self._device_id)

    def _fail(self, message: str) -> None:
        self._flow = None
        self._set_error(message or self.tr("Pairing didn't work. Try again."))
        self._set_state("failed")

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.stateChanged.emit()

    def _set_error(self, error: str) -> None:
        if error != self._error:
            self._error = error
            self.errorChanged.emit()


class AppViewModel(QObject):
    """Top-level state for the main window and the tray menu."""

    discoveringChanged = Signal()
    messageChanged = Signal()
    hiddenToTray = Signal()
    quitRequested = Signal()

    def __init__(
        self,
        backend: Backend,
        *,
        demo_mode: bool = False,
        reduce_motion: bool = False,
        can_hide_to_tray: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend = backend
        self._demo_mode = demo_mode
        self._reduce_motion = reduce_motion
        self._can_hide_to_tray = can_hide_to_tray
        self._discovering = False
        self._message = ""
        self._runner = TaskRunner(self._on_task_error)
        self._devices = DeviceListModel(self)
        self._pairing = PairingViewModel(backend, self._runner, self)
        self._pairing.paired.connect(self.connectDevice)
        self._unsubscribe: Callable[[], None] | None = None

    # Properties

    def _get_devices(self) -> DeviceListModel:
        return self._devices

    def _get_pairing(self) -> PairingViewModel:
        return self._pairing

    def _get_discovering(self) -> bool:
        return self._discovering

    def _get_message(self) -> str:
        return self._message

    def _get_demo_mode(self) -> bool:
        return self._demo_mode

    def _get_reduce_motion(self) -> bool:
        return self._reduce_motion

    def _get_can_hide_to_tray(self) -> bool:
        return self._can_hide_to_tray

    devices = Property(QObject, _get_devices, constant=True)
    pairing = Property(QObject, _get_pairing, constant=True)
    discovering = Property(bool, _get_discovering, notify=discoveringChanged)
    message = Property(str, _get_message, notify=messageChanged)
    demoMode = Property(bool, _get_demo_mode, constant=True)
    reduceMotion = Property(bool, _get_reduce_motion, constant=True)
    canHideToTray = Property(bool, _get_can_hide_to_tray, constant=True)

    @property
    def device_list(self) -> DeviceListModel:
        return self._devices

    @property
    def pairing_flow(self) -> PairingViewModel:
        return self._pairing

    @property
    def runner(self) -> TaskRunner:
        return self._runner

    # Lifecycle

    async def start(self) -> None:
        self._unsubscribe = self._backend.subscribe(self._on_event)
        for device in self._backend.devices():
            self._devices.upsert(device)
        await self._backend.start()

    async def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._pairing.close()
        await self._backend.stop()

    # Slots

    @Slot(str)
    def activate(self, device_id: str) -> None:
        """The card's main action: pair, connect, disconnect, or cancel a retry."""
        device = self._devices.snapshot(device_id)
        if device is None:
            return
        if device.needs_pairing:
            self.pairDevice(device_id)
        elif device.state in (LinkState.DISCONNECTED, LinkState.FAILED):
            self.connectDevice(device_id)
        elif device.state in (LinkState.CONNECTED, LinkState.WAITING):
            self.disconnectDevice(device_id)
        # CONNECTING: wait for the attempt to finish.

    @Slot(str)
    def connectDevice(self, device_id: str) -> None:
        self._runner.run(self._backend.connect(device_id))

    @Slot(str)
    def disconnectDevice(self, device_id: str) -> None:
        self._runner.run(self._backend.disconnect(device_id))

    @Slot(str)
    def pairDevice(self, device_id: str) -> None:
        device = self._devices.snapshot(device_id)
        if device is not None:
            self._pairing.open(device.id, device.name)

    @Slot()
    def dismissMessage(self) -> None:
        self._set_message("")

    @Slot()
    def windowHidden(self) -> None:
        self.hiddenToTray.emit()

    @Slot()
    def requestQuit(self) -> None:
        self.quitRequested.emit()

    # Internals

    def _on_event(self, event: BackendEvent) -> None:
        match event:
            case DeviceUpdated(device=device):
                self._devices.upsert(device)
            case DeviceRemoved(device_id=device_id):
                self._devices.remove(device_id)
                if self._pairing.device_id == device_id:
                    self._pairing.close()
            case DiscoveryChanged(active=active):
                if active != self._discovering:
                    self._discovering = active
                    self.discoveringChanged.emit()

    def _on_task_error(self, error: BaseException) -> None:
        if isinstance(error, PairingError) and str(error):
            self._set_message(str(error))
            return
        # Type name only: exception messages can contain addresses (docs/PRIVACY.md).
        _LOGGER.error("UI task failed: %s", type(error).__name__)
        self._set_message(self.tr("Something went wrong. Try again."))

    def _set_message(self, message: str) -> None:
        if message != self._message:
            self._message = message
            self.messageChanged.emit()
