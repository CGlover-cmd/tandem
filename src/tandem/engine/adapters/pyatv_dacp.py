"""pyatv side of speaker buttons (`engine.speaker_buttons`): one DACP identity, announced.

pyatv picks a random `DACP-ID` and `Active-Remote` for every RTSP session and serves nothing
on them. Tandem gives every session the same pair, from its `Identity`, and announces
`iTunes_Ctrl_<DACP-ID>` over mDNS so receivers can find its button server. The hand-over wraps
`pyatv.support.rtsp.RtspSession.__init__` once, like the audio source hook (ADR-0011): pyatv
is pinned to a minor version and a test checks the attributes still exist.

The announcement uses zeroconf, which HAP-python already brings (the Home bridge).
"""

from __future__ import annotations

import socket
from typing import Any

from pyatv.support import rtsp

from tandem.engine.network import read_addresses
from tandem.engine.speaker_buttons import SERVICE_TYPE, Identity

_original_init: Any = rtsp.RtspSession.__init__
_identity: Identity | None = None


def _init(self: Any, *args: Any, **kwargs: Any) -> None:
    _original_init(self, *args, **kwargs)
    if _identity is not None:
        self.dacp_id = _identity.dacp_id
        self.active_remote = int(_identity.active_remote)


def install_hook(identity: Identity) -> None:
    """Send `identity` to receivers from now on. Safe to call more than once."""
    global _identity
    _identity = identity
    if rtsp.RtspSession.__init__ is not _init:
        rtsp.RtspSession.__init__ = _init  # type: ignore[method-assign]


class ZeroconfAdvertiser:
    """Announces the button server as `_dacp._tcp` on the PC's addresses."""

    def __init__(self) -> None:
        self._zeroconf: Any = None
        self._info: Any = None

    async def publish(self, identity: Identity, port: int) -> None:
        from zeroconf import ServiceInfo
        from zeroconf.asyncio import AsyncZeroconf

        install_hook(identity)
        addresses = [socket.inet_aton(a) for a in sorted(read_addresses())]
        info = ServiceInfo(
            SERVICE_TYPE,
            f"{identity.service_name}.{SERVICE_TYPE}",
            port=port,
            addresses=addresses,
            properties={"txtvers": "1", "Ver": "131075", "DbId": identity.dacp_id},
            server=f"{socket.gethostname().split('.')[0] or 'tandem'}.local.",
        )
        self._zeroconf = AsyncZeroconf()
        await self._zeroconf.async_register_service(info)
        self._info = info

    async def close(self) -> None:
        zeroconf, self._zeroconf = self._zeroconf, None
        if zeroconf is None:
            return
        if self._info is not None:
            await zeroconf.async_unregister_service(self._info)
            self._info = None
        await zeroconf.async_close()
