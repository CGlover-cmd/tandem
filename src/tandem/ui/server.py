"""The loopback web server that carries the UI (ADR-0010).

It serves the built front end and one WebSocket. The page receives the full UI state after
every change and sends commands back; `AppController` does the rest.

Safety: the server listens on 127.0.0.1 only, so nothing on the network can reach it and
Windows shows no firewall prompt. Every request must name this server in its `Host` header
(stops DNS rebinding), and the WebSocket also needs this launch's random token and an
`Origin` of this server (stops other web pages and other local users driving it).
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import secrets
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from tandem.ui.controller import AppController

_LOGGER = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
"""Where `npm run build` in `web/` puts the front end."""

_MISSING_BUILD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Tandem</title></head>
<body style="font-family: 'Segoe UI', sans-serif; padding: 2rem">
<h1>The interface hasn't been built yet</h1>
<p>From the repository root, run <code>npm --prefix web install</code> and then
<code>npm --prefix web run build</code>, and start Tandem again.</p>
</body></html>
"""

_MAX_MESSAGE = 16 * 1024

# Only this server's own files and WebSocket; no remote scripts, frames or form targets.
_CSP = (
    "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; form-action 'none'"
)


class UiServer:
    def __init__(
        self,
        controller: AppController,
        *,
        static_dir: Path = STATIC_DIR,
        host: str = "127.0.0.1",
        port: int = 0,
        token: str | None = None,
        extra_origins: Iterable[str] = (),
    ) -> None:
        self._controller = controller
        self._static_dir = static_dir
        self._host = host
        self._port = port
        self.token = token or secrets.token_urlsafe(24)
        self._extra_origins = set(extra_origins)
        self._sockets: set[web.WebSocketResponse] = set()
        self._runner: web.AppRunner | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self._push_pending = False
        self._sends: set[asyncio.Task[None]] = set()

    @property
    def port(self) -> int:
        return self._port

    @property
    def origin(self) -> str:
        return f"http://{self._host}:{self._port}"

    @property
    def url(self) -> str:
        """The page address, token included. Don't log it: anyone with it can drive the UI."""
        return f"{self.origin}/?token={self.token}"

    def app(self) -> web.Application:
        app = web.Application(middlewares=[self._check_host], client_max_size=_MAX_MESSAGE)
        app.router.add_get("/ws", self._websocket)
        app.router.add_get("/", self._index)
        assets = self._static_dir / "assets"
        if assets.is_dir():
            app.router.add_static("/assets", assets)
        return app

    async def start(self) -> None:
        self._runner = web.AppRunner(self.app(), access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        if self._port == 0:
            self._port = int(self._runner.addresses[0][1])
        self._unsubscribe = self._controller.subscribe(self._schedule_push)

    async def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        for socket in list(self._sockets):
            await socket.close()
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    # Request handling

    def _allowed_hosts(self) -> set[str]:
        return {f"127.0.0.1:{self._port}", f"localhost:{self._port}"}

    def _allowed_origins(self) -> set[str]:
        return {f"http://{host}" for host in self._allowed_hosts()} | self._extra_origins

    @web.middleware
    async def _check_host(self, request: web.Request, handler: Any) -> web.StreamResponse:
        if request.host not in self._allowed_hosts():
            raise web.HTTPMisdirectedRequest()
        response: web.StreamResponse = await handler(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Content-Security-Policy", _CSP)
        return response

    async def _index(self, _request: web.Request) -> web.StreamResponse:
        index = self._static_dir / "index.html"
        if not index.is_file():
            return web.Response(text=_MISSING_BUILD, content_type="text/html")
        return web.FileResponse(index)

    async def _websocket(self, request: web.Request) -> web.StreamResponse:
        token = request.query.get("token", "")
        if not hmac.compare_digest(token.encode(), self.token.encode()):
            raise web.HTTPForbidden()
        if request.headers.get("Origin") not in self._allowed_origins():
            raise web.HTTPForbidden()

        socket = web.WebSocketResponse(heartbeat=20, max_msg_size=_MAX_MESSAGE)
        await socket.prepare(request)
        self._sockets.add(socket)
        try:
            await self._send(socket, self._state_message())
            async for message in socket:
                if message.type is WSMsgType.TEXT:
                    self._on_command(message.data)
        finally:
            self._sockets.discard(socket)
        return socket

    def _on_command(self, raw: str) -> None:
        try:
            command = json.loads(raw)
        except ValueError:
            _LOGGER.debug("Ignoring a message that isn't JSON")
            return
        if isinstance(command, dict):
            self._controller.handle(command)  # pyright: ignore[reportUnknownArgumentType]

    # Pushing state

    def _state_message(self) -> str:
        return json.dumps({"type": "state", "state": self._controller.snapshot()})

    def _schedule_push(self) -> None:
        """Coalesce a burst of changes into one push on the next loop turn."""
        if self._push_pending or not self._sockets:
            return
        self._push_pending = True
        asyncio.get_running_loop().call_soon(self._push)

    def _push(self) -> None:
        self._push_pending = False
        message = self._state_message()
        loop = asyncio.get_running_loop()
        for socket in list(self._sockets):
            task = loop.create_task(self._send(socket, message))
            self._sends.add(task)
            task.add_done_callback(self._sends.discard)

    async def _send(self, socket: web.WebSocketResponse, message: str) -> None:
        if socket.closed:
            return
        try:
            await socket.send_str(message)
        except (ConnectionError, RuntimeError):
            self._sockets.discard(socket)
