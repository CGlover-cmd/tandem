"""The "Can't find a speaker?" sheet and speaker passwords on the real engine (lessons from
AirParrot; ADR-0023). Part of `tandem.bridge`, mixed into `EngineBackend`; it needs the engine
and the backend's publisher.

Addresses and passwords are private: shown in the window (addresses only), never logged.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from tandem.engine import net_check
from tandem.engine.addresses import AddressError
from tandem.engine.service import Engine, UnknownDeviceError
from tandem.ui import backend as ui

_LOGGER = logging.getLogger(__name__)

Problem = ui.Problem

_ADDRESS_PROBLEM = {
    AddressError.INVALID: Problem.BAD_ADDRESS,
    AddressError.NOT_LOCAL: Problem.NOT_LOCAL_ADDRESS,
    AddressError.TOO_MANY: Problem.TOO_MANY_ADDRESSES,
    AddressError.NO_ANSWER: Problem.NO_SPEAKER_THERE,
}
_FINDING = {f: ui.NetworkFinding(f.value) for f in net_check.Finding}

MAX_PASSWORD = 128


class EngineNetwork:
    """Speakers by address, the network check and speaker passwords, for `EngineBackend`."""

    _engine: Engine
    _publish: Callable[[ui.BackendEvent], None]

    def _init_network(self) -> None:
        self._adding = False
        self._checking = False
        self._findings: tuple[ui.NetworkFinding, ...] | None = None
        self._seen = 0

    def network(self) -> ui.NetworkSnapshot:
        return ui.NetworkSnapshot(
            addresses=tuple(self._engine.addresses.addresses()),
            adding=self._adding,
            checking=self._checking,
            findings=self._findings,
            speakers_seen=self._seen,
        )

    def _network_changed(self) -> None:
        self._publish(ui.NetworkChanged(self.network()))

    async def add_speaker_address(self, address: str) -> None:
        self._adding = True
        self._network_changed()
        try:
            await self._engine.add_address(address)
        except AddressError as error:
            raise ui.BackendError(_ADDRESS_PROBLEM[error.reason]) from None
        except OSError as exc:
            _LOGGER.info("Asking an address failed (%s)", type(exc).__name__)
            raise ui.BackendError(Problem.NO_SPEAKER_THERE) from None
        finally:
            self._adding = False
            self._network_changed()

    async def remove_speaker_address(self, address: str) -> None:
        self._engine.remove_address(address)
        self._network_changed()

    async def check_network(self) -> None:
        if self._checking:
            return
        self._checking = True
        self._network_changed()
        try:
            report = await self._engine.check_network()
            self._findings = tuple(_FINDING[f] for f in report.findings)
            self._seen = report.speakers_seen
        finally:
            self._checking = False
            self._network_changed()

    async def set_speaker_password(self, device_id: str, password: str) -> None:
        password = password[:MAX_PASSWORD]
        if not password:
            return
        try:
            await self._engine.set_password(device_id, password)
        except UnknownDeviceError:
            raise ui.AudioError(Problem.SPEAKER_GONE) from None
        except OSError as exc:
            _LOGGER.info("Saving a speaker password failed (%s)", type(exc).__name__)
            raise ui.AudioError(Problem.NO_AUDIO) from None
        if device_id in self._engine.outputs.failed():
            try:
                await self._engine.outputs.start(device_id)
            except Exception as exc:
                _LOGGER.info("The speaker didn't play with its password (%s)", type(exc).__name__)
