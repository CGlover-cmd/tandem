"""In-process event bus.

Engine components publish events (frozen dataclasses deriving from `Event`); the UI and the
command-line tool subscribe to them. Everything runs on the asyncio loop thread, so `publish`
calls handlers synchronously and in subscription order. A failing handler is logged and never
stops delivery to the others.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, suppress
from typing import Any, TypeVar

_LOGGER = logging.getLogger(__name__)


class Event:
    """Base class for engine events. Subscribing to a base class receives its subclasses."""

    __slots__ = ()


E = TypeVar("E", bound=Event)
Unsubscribe = Callable[[], None]


class EventBus:
    """Publish/subscribe dispatch keyed by event type."""

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[Callable[[Any], None]]] = {}

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> Unsubscribe:
        """Call `handler` for each published `event_type` (or subclass); returns an unsubscriber."""
        handlers = self._handlers.setdefault(event_type, [])
        handlers.append(handler)

        def unsubscribe() -> None:
            with suppress(ValueError):
                handlers.remove(handler)

        return unsubscribe

    def publish(self, event: Event) -> None:
        """Deliver `event` to its subscribers, most specific type first."""
        for cls in type(event).__mro__:
            if not issubclass(cls, Event):
                continue
            for handler in list(self._handlers.get(cls, ())):
                try:
                    handler(event)
                except Exception:
                    _LOGGER.exception("Event handler failed for %s", type(event).__name__)

    @asynccontextmanager
    async def listen(self, event_type: type[E]) -> AsyncGenerator[asyncio.Queue[E]]:
        """Collect `event_type` events in a queue for as long as the context is open."""
        queue: asyncio.Queue[E] = asyncio.Queue()
        unsubscribe = self.subscribe(event_type, queue.put_nowait)
        try:
            yield queue
        finally:
            unsubscribe()

    async def wait_for(
        self,
        event_type: type[E],
        predicate: Callable[[E], bool] = lambda _event: True,
        timeout: float | None = None,
    ) -> E:
        """Wait for the next `event_type` event that matches `predicate`."""
        future: asyncio.Future[E] = asyncio.get_running_loop().create_future()

        def handler(event: E) -> None:
            if not future.done() and predicate(event):
                future.set_result(event)

        unsubscribe = self.subscribe(event_type, handler)
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            unsubscribe()
