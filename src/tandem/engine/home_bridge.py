"""Tandem as a bridge in the Home app (Phase 10b, ADR-0014, ADR-0016).

When the user turns it on, Tandem shows up in the Home app as a bridge with a few switches.
Siri on a HomePod ("turn on Tandem Audio") and Home automations can then drive Tandem, which is
how Siri reaches a Windows app at all (ADR-0014). The switches have fixed, generic names, so no
device or room name leaves the PC.

The HomeKit side (HAP) is an adapter (`adapters/hap_bridge.py`); this module keeps the switch
list, follows Tandem's state into the switches, and runs a switch's action when the Home app
flips it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

from tandem.engine.events import Event, EventBus

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SwitchSpec:
    id: str
    name: str
    """Shown in the Home app and matched by the command bar ("turn on tandem audio")."""


SWITCHES = (
    SwitchSpec("audio", "Tandem Audio"),
    SwitchSpec("music", "Tandem Music"),
    SwitchSpec("tv", "Tandem TV"),
)
"""Audio: send the PC's sound to the speakers used last. Music: Tandem's player. TV: the Apple
TV's power."""


@dataclass(frozen=True, slots=True)
class HomeStatus:
    enabled: bool = False
    running: bool = False
    paired: bool = False
    setup_code: str | None = None
    """The 8-digit code to type into the Home app; shown only until the bridge is added."""
    error: str | None = None
    switches: tuple[tuple[str, str, bool], ...] = ()
    """(id, name, on) for each switch."""


@dataclass(frozen=True, slots=True)
class HomeChanged(Event):
    status: HomeStatus = HomeStatus()


class BridgeServer(Protocol):
    """The HomeKit accessory server (HAP-python, in `adapters`)."""

    async def start(
        self, switches: Sequence[SwitchSpec], on_set: Callable[[str, bool], None]
    ) -> str:
        """Start advertising; returns the setup code. `on_set` runs when the Home app flips
        a switch."""
        ...

    async def stop(self) -> None: ...

    def set_state(self, switch_id: str, on: bool) -> None:
        """Show a switch's state in the Home app (Tandem changed it, not the Home app)."""
        ...

    @property
    def paired(self) -> bool: ...


class HomeActions(Protocol):
    def switch_states(self) -> dict[str, bool]:
        """Each switch's state, from Tandem's own state."""
        ...

    async def set_switch(self, switch_id: str, on: bool) -> None: ...


class HomeBridge:
    def __init__(
        self,
        bus: EventBus,
        server: Callable[[], BridgeServer],
        actions: HomeActions,
    ) -> None:
        self._bus = bus
        self._server_factory = server
        self._actions = actions
        self._server: BridgeServer | None = None
        self._code: str | None = None
        self._enabled = False
        self._error: str | None = None
        self._shown: dict[str, bool] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def status(self) -> HomeStatus:
        states = self._actions.switch_states()
        paired = self._server is not None and self._server.paired
        return HomeStatus(
            enabled=self._enabled,
            running=self._server is not None,
            paired=paired,
            setup_code=None if paired else self._code,
            error=self._error,
            switches=tuple((s.id, s.name, states.get(s.id, False)) for s in SWITCHES),
        )

    @property
    def running(self) -> bool:
        return self._server is not None

    async def start(self) -> None:
        self._enabled = True
        if self._server is not None:
            return
        server = self._server_factory()
        try:
            self._code = await server.start(SWITCHES, self._on_set)
        except Exception as exc:  # a busy port, no network
            _LOGGER.warning("The Home bridge didn't start (%s)", type(exc).__name__)
            self._error = type(exc).__name__
            self._publish()
            return
        self._server = server
        self._error = None
        self._shown = {}
        self.refresh()

    async def stop(self) -> None:
        self._enabled = False
        server, self._server = self._server, None
        for task in list(self._tasks):
            task.cancel()
        if server is not None:
            with suppress(Exception):
                await server.stop()
        self._code = None
        self._publish()

    def refresh(self) -> None:
        """Follow Tandem's state into the switches (call after anything they reflect)."""
        server = self._server
        if server is not None:
            for switch_id, on in self._actions.switch_states().items():
                if self._shown.get(switch_id) != on:
                    self._shown[switch_id] = on
                    server.set_state(switch_id, on)
        self._publish()

    async def set_switch(self, switch_id: str, on: bool) -> None:
        """Flip a switch from Tandem itself (the command bar)."""
        await self._actions.set_switch(switch_id, on)
        self.refresh()

    def _on_set(self, switch_id: str, on: bool) -> None:
        self._shown[switch_id] = on
        task = asyncio.get_running_loop().create_task(self._run(switch_id, on))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, switch_id: str, on: bool) -> None:
        try:
            await self._actions.set_switch(switch_id, on)
        except Exception as exc:
            _LOGGER.info("A Home switch's action failed (%s)", type(exc).__name__)
        self.refresh()

    def _publish(self) -> None:
        self._bus.publish(HomeChanged(self.status()))


Action = Callable[[bool], Awaitable[None]]
