"""A speaker's own buttons control Tandem: the receiver-to-sender half of AirPlay audio (DACP).

An AirPlay audio sender tells each receiver two things with every request: a `DACP-ID` and an
`Active-Remote` token. A receiver that has buttons (a HomePod's touch surface, a soundbar's
remote, a TV's volume keys) looks for a `_dacp._tcp` service named `iTunes_Ctrl_<DACP-ID>` on
the network and sends `GET /ctrl-int/1/<command>` there, with the token in an `Active-Remote`
header. Some receivers also report their own volume changes the same way
(`setproperty?dmcp.device-volume=...`). This is the public, documented-by-the-community side
of AirPlay ("Audio speakers can send commands to the AirPlay client"); no keys are involved.

Tandem answers on a small local web server and passes each command on: play, pause and skip go
to whatever the PC is playing (or Tandem's own player), volume keys change that speaker's
volume in Tandem, and a speaker's reported volume is shown. Requests without the token are
refused. Whether HomePods send these to a sender that isn't Apple's is unverified on
hardware: if they don't, nothing happens and nothing breaks.

Speaker addresses are private: never logged.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

_LOGGER = logging.getLogger(__name__)

SERVICE_TYPE = "_dacp._tcp.local."


class ButtonCommand(Enum):
    PLAY = "play"
    PAUSE = "pause"
    PLAY_PAUSE = "playpause"
    NEXT = "nextitem"
    PREVIOUS = "previtem"
    STOP = "stop"
    VOLUME_UP = "volumeup"
    VOLUME_DOWN = "volumedown"
    VOLUME = "volume"  # the speaker reports its own level (0 to 100 in `ButtonPress.level`)


@dataclass(frozen=True, slots=True)
class ButtonPress:
    command: ButtonCommand
    level: float | None = None


_ALIASES = {"playresume": ButtonCommand.PLAY, "mutetoggle": None, "beginff": None}


def parse(command: str, query: Mapping[str, str]) -> ButtonPress | None:
    """What a `/ctrl-int/1/<command>?<query>` request asks for; None if Tandem ignores it."""
    command = command.strip().lower()
    if command == "setproperty":
        return _volume_from(query)
    if command in _ALIASES:
        alias = _ALIASES[command]
        return None if alias is None else ButtonPress(alias)
    try:
        found = ButtonCommand(command)
    except ValueError:
        return None
    return None if found is ButtonCommand.VOLUME else ButtonPress(found)


def _volume_from(query: Mapping[str, str]) -> ButtonPress | None:
    if "dmcp.volume" in query:  # 0 to 100
        level = _number(query["dmcp.volume"])
        if level is not None:
            return ButtonPress(ButtonCommand.VOLUME, max(0.0, min(100.0, level)))
    if "dmcp.device-volume" in query:  # decibels: -30 (quiet) to 0 (full), -144 is muted
        db = _number(query["dmcp.device-volume"])
        if db is not None:
            level = 0.0 if db <= -30 else (db + 30) / 30 * 100
            return ButtonPress(ButtonCommand.VOLUME, max(0.0, min(100.0, level)))
    return None


def _number(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value == value else None  # NaN


@dataclass(frozen=True, slots=True)
class Identity:
    """What Tandem tells receivers, the same for every stream in one run."""

    dacp_id: str
    """16 hex digits; the service name is `iTunes_Ctrl_<dacp_id>`."""
    active_remote: str
    """The token a receiver must send back; a decimal number."""

    @classmethod
    def new(cls) -> Identity:
        return cls(f"{secrets.randbits(64):016X}", str(secrets.randbits(32)))

    @property
    def service_name(self) -> str:
        return f"iTunes_Ctrl_{self.dacp_id}"


class Advertiser(Protocol):
    """Announces the remote-control service on the local network (mDNS)."""

    async def publish(self, identity: Identity, port: int) -> None: ...

    async def close(self) -> None: ...


Handler = Callable[[str, ButtonPress], Awaitable[None]]
"""Called with the speaker's address (private) and what it asked for."""


class SpeakerButtons:
    """The local web server receivers send their button presses to."""

    def __init__(
        self,
        advertiser: Advertiser | None,
        *,
        identity: Identity | None = None,
        host: str = "0.0.0.0",
        port: int = 0,
    ) -> None:
        self.identity = identity or Identity.new()
        self._advertiser = advertiser
        self._host = host
        self._port = port
        self._runner: Any = None
        self._handler: Handler | None = None
        self.port = 0
        self.presses = 0
        """Accepted requests so far (diagnostics: shows whether a speaker ever sent any)."""

    @property
    def running(self) -> bool:
        return self._runner is not None

    async def start(self, handler: Handler) -> None:
        if self._runner is not None:
            return
        from aiohttp import web

        self._handler = handler
        app = web.Application()
        app.router.add_get("/ctrl-int/1/{command}", self._serve)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._port)
        try:
            await site.start()
        except BaseException:
            await runner.cleanup()
            raise
        address: Any = runner.addresses[0]
        self.port = int(address[1])
        self._runner = runner
        if self._advertiser is not None:
            try:
                await self._advertiser.publish(self.identity, self.port)
            except Exception as exc:
                _LOGGER.info("Couldn't announce speaker buttons (%s)", type(exc).__name__)

    async def stop(self) -> None:
        runner, self._runner = self._runner, None
        if self._advertiser is not None:
            try:
                await self._advertiser.close()
            except Exception as exc:
                _LOGGER.debug("Closing the announcement failed (%s)", type(exc).__name__)
        if runner is not None:
            await runner.cleanup()

    async def _serve(self, request: Any) -> Any:
        from aiohttp import web

        if request.headers.get("Active-Remote", "") != self.identity.active_remote:
            raise web.HTTPForbidden()
        press = parse(request.match_info["command"], dict(request.query))
        if press is not None and self._handler is not None:
            self.presses += 1
            _LOGGER.info("A speaker sent %s", press.command.value)
            try:
                await self._handler(str(request.remote or ""), press)
            except Exception as exc:
                _LOGGER.info("A speaker's button didn't work (%s)", type(exc).__name__)
        return web.Response(status=204)
