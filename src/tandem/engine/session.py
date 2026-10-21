"""Connection state machine: connect, notice drops, reconnect with backoff.

One `ConnectionSession` looks after one device. It is protocol-agnostic: the actual work of
opening a connection is done by a `Connector` (the pyatv one lives in `adapters`).

    DISCONNECTED --start()--> CONNECTING --ok--> CONNECTED --lost--> WAITING --> CONNECTING ...
                                   |                                    ^
                                   +--failed----------------------------+
                                   +--failed max_attempts times--> FAILED
    any state --close()--> DISCONNECTED
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from tandem.engine.backoff import Backoff
from tandem.engine.events import Event, EventBus

_LOGGER = logging.getLogger(__name__)

_CLOSE_TIMEOUT = 5.0


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    WAITING = "waiting"  # waiting to retry after a failed attempt or a dropped connection
    FAILED = "failed"  # gave up after max_attempts failed attempts in a row


@dataclass(frozen=True, slots=True)
class ConnectionStateChanged(Event):
    device_id: str
    state: ConnectionState
    previous: ConnectionState
    attempt: int = 0
    """Failed attempts in a row so far."""
    retry_in: float | None = None
    """Seconds until the next attempt, when `state` is WAITING."""
    reason: str | None = None
    """Exception type name only: messages can contain addresses (docs/PRIVACY.md)."""


class Link(Protocol):
    """An open connection to a device."""

    async def close(self) -> None: ...


LostCallback = Callable[[BaseException | None], None]
"""Called by a link when its connection drops (with the error, if any)."""

Connector = Callable[[LostCallback], Awaitable[Link]]
"""Open a connection; call the given callback if it later drops."""

Sleep = Callable[[float], Awaitable[None]]


class ConnectionFailedError(Exception):
    """The session gave up, or was closed, before it connected."""


class ConnectionSession:
    def __init__(
        self,
        device_id: str,
        connector: Connector,
        bus: EventBus,
        *,
        backoff: Backoff | None = None,
        max_attempts: int | None = None,
        connect_timeout: float = 15.0,
        sleep: Sleep = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        if max_attempts is not None and max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.device_id = device_id
        self._connector = connector
        self._bus = bus
        self._backoff = backoff or Backoff()
        self._max_attempts = max_attempts
        self._connect_timeout = connect_timeout
        self._sleep = sleep
        self._rng = rng
        self._state = ConnectionState.DISCONNECTED
        self._link: Link | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def link(self) -> Link | None:
        """The open connection while CONNECTED, otherwise None."""
        return self._link

    def start(self) -> None:
        """Connect, and keep reconnecting after drops until `close()`. Idempotent."""
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(
                self._supervise(), name="connection-session"
            )

    async def close(self) -> None:
        """Disconnect and stop reconnecting."""
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._set(ConnectionState.DISCONNECTED)

    async def wait_connected(self, timeout: float | None = None) -> Link:
        """Wait until CONNECTED and return the link. Raises ConnectionFailedError on FAILED
        or DISCONNECTED, and TimeoutError after `timeout` seconds."""
        if self._state is ConnectionState.CONNECTED and self._link is not None:
            return self._link
        if self._state in (ConnectionState.FAILED, ConnectionState.DISCONNECTED) and not (
            self._task and not self._task.done()
        ):
            raise ConnectionFailedError(self._state.value)
        settled = (ConnectionState.CONNECTED, ConnectionState.FAILED, ConnectionState.DISCONNECTED)
        event = await self._bus.wait_for(
            ConnectionStateChanged,
            lambda e: e.device_id == self.device_id and e.state in settled,
            timeout,
        )
        if event.state is ConnectionState.CONNECTED and self._link is not None:
            return self._link
        raise ConnectionFailedError(event.state.value)

    def _set(
        self,
        state: ConnectionState,
        *,
        attempt: int = 0,
        retry_in: float | None = None,
        reason: str | None = None,
    ) -> None:
        previous, self._state = self._state, state
        if previous is state:
            return
        self._bus.publish(
            ConnectionStateChanged(self.device_id, state, previous, attempt, retry_in, reason)
        )

    async def _supervise(self) -> None:
        try:
            await self._run()
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Connection supervisor for %s crashed", self.device_id)
            self._set(ConnectionState.FAILED, reason="InternalError")

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        failures = 0
        while True:
            self._set(ConnectionState.CONNECTING, attempt=failures)
            lost = asyncio.Event()
            lost_reason: list[str] = []

            def on_lost(
                exc: BaseException | None,
                lost: asyncio.Event = lost,
                lost_reason: list[str] = lost_reason,
            ) -> None:
                lost_reason.append(type(exc).__name__ if exc else "ConnectionClosed")
                loop.call_soon_threadsafe(lost.set)

            try:
                link = await asyncio.wait_for(self._connector(on_lost), self._connect_timeout)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failures += 1
                reason = type(exc).__name__
                _LOGGER.info("Connecting to %s failed (%s)", self.device_id, reason)
                if self._max_attempts is not None and failures >= self._max_attempts:
                    self._set(ConnectionState.FAILED, attempt=failures, reason=reason)
                    return
                delay = self._backoff.delay(failures - 1, self._rng)
                self._set(ConnectionState.WAITING, attempt=failures, retry_in=delay, reason=reason)
                await self._sleep(delay)
                continue

            failures = 0
            self._link = link
            self._set(ConnectionState.CONNECTED)
            try:
                await lost.wait()
            finally:
                self._link = None
                await self._close_link(link)

            reason = lost_reason[0] if lost_reason else "ConnectionClosed"
            _LOGGER.info("Connection to %s dropped (%s)", self.device_id, reason)
            delay = self._backoff.delay(0, self._rng)
            self._set(ConnectionState.WAITING, retry_in=delay, reason=reason)
            await self._sleep(delay)

    async def _close_link(self, link: Link) -> None:
        try:
            await asyncio.wait_for(link.close(), _CLOSE_TIMEOUT)
        except Exception as exc:
            _LOGGER.debug("Closing link to %s failed (%s)", self.device_id, type(exc).__name__)
