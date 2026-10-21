from __future__ import annotations

import asyncio
import logging

import pytest
from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QApplication

from tandem.ui.backend import DeviceKind, DeviceSnapshot, LinkState, PairingError, PairingFlow
from tandem.ui.demo_backend import WRONG_PIN, DemoBackend
from tandem.ui.viewmodels import AppViewModel, DeviceListModel

pytestmark = pytest.mark.usefixtures("qapp")


def _device(device_id: str, name: str, **kwargs: object) -> DeviceSnapshot:
    return DeviceSnapshot(device_id, name, DeviceKind.HOMEPOD, **kwargs)  # type: ignore[arg-type]


def _names(model: DeviceListModel) -> list[str]:
    return [d.name for d in model.snapshots()]


async def _settle(vm: AppViewModel) -> None:
    await vm.runner.drain()


async def _started(backend: DemoBackend) -> AppViewModel:
    vm = AppViewModel(backend, demo_mode=True)
    await vm.start()
    return vm


# DeviceListModel


def test_model_keeps_rows_sorted_by_name() -> None:
    model = DeviceListModel()
    model.upsert(_device("b", "loft"))
    model.upsert(_device("a", "Gallery"))
    model.upsert(_device("c", "Attic"))

    assert _names(model) == ["Attic", "Gallery", "loft"]
    assert model.rowCount() == 3


def test_model_updates_in_place_and_resorts_on_rename() -> None:
    model = DeviceListModel()
    model.upsert(_device("a", "Gallery"))
    model.upsert(_device("b", "Loft"))
    changed: list[int] = []

    def on_changed(top: QModelIndex, _bottom: QModelIndex) -> None:
        changed.append(top.row())

    model.dataChanged.connect(on_changed)

    model.upsert(_device("a", "Gallery", state=LinkState.CONNECTED))
    model.upsert(_device("a", "Zen Room"))

    assert changed == [0]
    assert _names(model) == ["Loft", "Zen Room"]


def test_model_exposes_roles_to_qml() -> None:
    model = DeviceListModel()
    model.upsert(_device("a", "Gallery", state=LinkState.WAITING, retry_in=2.0))
    index = model.index(0)

    assert model.data(index, DeviceListModel.StateRole) == "waiting"
    assert model.data(index, DeviceListModel.KindRole) == "homepod"
    assert model.data(index, DeviceListModel.RetryInRole) == 2.0
    assert b"linkState" in [bytes(name.data()) for name in model.roleNames().values()]


def test_model_remove() -> None:
    model = DeviceListModel()
    model.upsert(_device("a", "Gallery"))
    model.remove("a")
    model.remove("missing")

    assert model.rowCount() == 0


# AppViewModel


async def test_start_fills_the_model(backend: DemoBackend) -> None:
    vm = await _started(backend)

    assert vm.device_list.rowCount() == 4
    assert vm.discovering is False


async def test_activate_connects_then_disconnects(backend: DemoBackend) -> None:
    vm = await _started(backend)

    vm.activate("demo-speaker-1")
    await _settle(vm)
    assert vm.device_list.snapshot("demo-speaker-1").state is LinkState.CONNECTED  # type: ignore[union-attr]

    vm.activate("demo-speaker-1")
    await _settle(vm)
    assert vm.device_list.snapshot("demo-speaker-1").state is LinkState.DISCONNECTED  # type: ignore[union-attr]


async def test_activate_on_unpaired_tv_opens_pairing(backend: DemoBackend) -> None:
    vm = await _started(backend)

    vm.activate("demo-tv")

    assert vm.pairing_flow.state == "starting"
    assert vm.pairing_flow.deviceName == "Living Room TV"
    await _settle(vm)
    assert vm.pairing_flow.state == "enterPin"


async def test_pairing_retries_wrong_pin_then_connects(backend: DemoBackend) -> None:
    vm = await _started(backend)
    pairing = vm.pairing_flow
    vm.pairDevice("demo-tv")
    await _settle(vm)

    pairing.submitPin(WRONG_PIN)
    await _settle(vm)
    assert pairing.state == "enterPin"
    assert "didn't match" in str(pairing.property("error"))

    pairing.submitPin("4821")
    await _settle(vm)
    assert pairing.state == "done"
    assert pairing.error == ""
    tv = vm.device_list.snapshot("demo-tv")
    assert tv is not None
    assert not tv.needs_pairing
    assert tv.state is LinkState.CONNECTED  # pairing connects straight away

    pairing.close()
    assert pairing.state == "closed"


async def test_pin_must_be_four_digits(backend: DemoBackend) -> None:
    vm = await _started(backend)
    vm.pairDevice("demo-tv")
    await _settle(vm)

    vm.pairing_flow.submitPin("12a")

    assert vm.pairing_flow.state == "enterPin"
    assert vm.pairing_flow.error != ""


async def test_cancel_while_starting_ignores_the_late_result(backend: DemoBackend) -> None:
    vm = await _started(backend)
    vm.pairDevice("demo-tv")

    vm.pairing_flow.cancel()
    await _settle(vm)

    assert vm.pairing_flow.state == "closed"


async def test_pairing_that_cannot_start_shows_failed(backend: DemoBackend) -> None:
    vm = await _started(backend)
    vm.pairing_flow.open("demo-speaker-1", "Patio Speaker")
    await _settle(vm)

    assert vm.pairing_flow.state == "failed"
    assert vm.pairing_flow.error != ""


async def test_device_leaving_closes_its_pairing_sheet(backend: DemoBackend) -> None:
    vm = await _started(backend)
    vm.pairDevice("demo-tv")
    await _settle(vm)

    backend.remove("demo-tv")

    assert vm.pairing_flow.state == "closed"
    assert vm.device_list.snapshot("demo-tv") is None


class _BrokenBackend(DemoBackend):
    async def connect(self, device_id: str) -> None:
        raise OSError("connection refused by 192.0.2.10")

    async def begin_pairing(self, device_id: str) -> PairingFlow:
        raise PairingError("")


async def test_unexpected_errors_show_a_generic_message_and_log_no_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    vm = await _started(_BrokenBackend(sleep=lambda _s: asyncio.sleep(0)))
    messages: list[str] = []
    vm.messageChanged.connect(lambda: messages.append(str(vm.property("message"))))

    with caplog.at_level(logging.ERROR):
        vm.activate("demo-speaker-1")
        await _settle(vm)

    assert messages == ["Something went wrong. Try again."]
    assert "192.0.2.10" not in caplog.text
    assert "OSError" in caplog.text

    vm.dismissMessage()
    assert vm.message == ""


async def test_stop_unsubscribes(backend: DemoBackend) -> None:
    vm = await _started(backend)
    await vm.stop()

    backend.remove("demo-speaker-1")

    assert vm.device_list.snapshot("demo-speaker-1") is not None


def test_qapp_fixture_is_a_widgets_app(qapp: QApplication) -> None:
    assert isinstance(qapp, QApplication)
