"""Cast screen on the real engine (part of `tandem.bridge`, ADR-0008; ADR-0006 addendum).

`EngineCast` is mixed into `EngineBackend`. It maps the engine's screen casts to the window's
contract: one cast at a time, its state and, when it fails, a problem code. Starting a cast
reports problems in that state rather than raising, so the sheet shows them in place.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from tandem.engine import pairing as engine_pairing
from tandem.engine import screen_cast as sc
from tandem.engine.service import Engine, UnknownDeviceError
from tandem.ui import backend as ui

_LOGGER = logging.getLogger(__name__)

_STATE = {
    sc.CastState.STARTING: ui.CastState.STARTING,
    sc.CastState.PLAYING: ui.CastState.PLAYING,
    sc.CastState.ENDED: ui.CastState.ENDED,
    sc.CastState.FAILED: ui.CastState.FAILED,
}
_QUALITY = {
    ui.CastQuality.LOW: sc.CastQuality.LOW,
    ui.CastQuality.STANDARD: sc.CastQuality.STANDARD,
    ui.CastQuality.HIGH: sc.CastQuality.HIGH,
}
_PROBLEM = {
    sc.CastError.NOT_A_TV: ui.Problem.NOT_A_TV,
    sc.CastError.NO_SCREEN: ui.Problem.NO_SCREEN,
    sc.CastError.ENCODER: ui.Problem.CAST_FAILED,
}


def problem_for(reason: str | None) -> str:
    """A cast's failure reason as the window's problem code. Anything that isn't one of the
    engine's own reasons came from the TV's side (it refused, or stopped answering)."""
    return _PROBLEM.get(reason or "", ui.Problem.CAST_REFUSED)


class EngineCast:
    """Screen casting, for `EngineBackend`."""

    _engine: Engine
    _publish: Callable[[ui.BackendEvent], None]

    def _init_cast(self) -> list[Callable[[], None]]:
        self._cast: ui.CastSnapshot | None = None
        return [self._engine.bus.subscribe(sc.ScreenCastChanged, self._on_cast)]

    async def screens(self) -> list[ui.ScreenInfo]:
        try:
            found = await asyncio.to_thread(self._engine.screens)
        except Exception as exc:  # the PC's displays are a nicety to list, never fatal
            _LOGGER.info("Listing screens failed (%s)", type(exc).__name__)
            return []
        return [ui.ScreenInfo(s.index, s.width, s.height, s.primary) for s in found]

    def cast(self) -> ui.CastSnapshot | None:
        return self._cast

    async def cast_screen(
        self, device_id: str, screen: int, quality: ui.CastQuality, sound: bool
    ) -> None:
        device = self._engine.registry.get(device_id)
        if device is None:
            self._set_cast(ui.CastSnapshot(device_id, ui.CastState.FAILED, ui.Problem.SPEAKER_GONE))
            return
        if engine_pairing.services_to_pair(device):
            self._set_cast(ui.CastSnapshot(device_id, ui.CastState.FAILED, ui.Problem.PAIR_FIRST))
            return
        # Connecting can take a while: show it starting at once.
        self._set_cast(ui.CastSnapshot(device_id, ui.CastState.STARTING))
        try:
            await self._engine.cast_screen(
                device_id, quality=_QUALITY[quality], screen=screen, sound=sound
            )
        except sc.CastError as error:
            self._fail(device_id, problem_for(error.reason))
        except UnknownDeviceError:
            self._fail(device_id, ui.Problem.SPEAKER_GONE)
        except (OSError, TimeoutError) as exc:
            _LOGGER.info("Casting the screen failed (%s)", type(exc).__name__)
            self._fail(device_id, ui.Problem.NOT_CONNECTED)

    async def stop_cast(self) -> None:
        await self._engine.stop_cast()

    # Engine events

    def _on_cast(self, event: sc.ScreenCastChanged) -> None:
        problem = problem_for(event.reason) if event.state is sc.CastState.FAILED else None
        self._set_cast(ui.CastSnapshot(event.device_id, _STATE[event.state], problem))

    def _fail(self, device_id: str, problem: str) -> None:
        current = self._cast
        if current is not None and current.device_id == device_id and current.problem:
            return  # the engine already said why
        self._set_cast(ui.CastSnapshot(device_id, ui.CastState.FAILED, problem))

    def _set_cast(self, cast: ui.CastSnapshot) -> None:
        if cast != self._cast:
            self._cast = cast
            self._publish(ui.CastChanged(cast))
