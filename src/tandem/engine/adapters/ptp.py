"""A small PTP (IEEE 1588) master clock for AirPlay 2 receivers (ADR-0022).

AirPlay 2 speakers that advertise `SupportsPTP` can follow a sender's PTP clock. Then every
speaker knows the same time, and a sync packet that says "audio sample R plays at time T"
means the same moment on all of them, so they play together without per-speaker delays.

This is not a full PTP clock. Like OwnTone's libairptp (MIT licence, (c) 2026 OwnTone), which
this module follows message for message, it always acts as the grandmaster and never adjusts
to anyone else: it announces itself as a very good clock, so receivers pick it, and it sends
two-step Sync / Follow_Up to each receiver, answers their Delay_Req, and sends the Signaling
message iOS sends. Messages go by unicast to the receivers named in each stream's SETUP reply.

The clock is `time.perf_counter_ns`, the Windows high-resolution counter. `time.monotonic` is
only 15.6 ms fine on Python 3.11 for Windows, too coarse for timestamps.

Ports are PTP's standard UDP 319 (event) and 320 (general). Windows lets any program bind
them; the installer's firewall rule is for the program, so it already covers them.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import struct
from collections.abc import Callable
from dataclasses import dataclass, field

from tandem.engine import timeline

_LOG = logging.getLogger(__name__)

EVENT_PORT = 319
GENERAL_PORT = 320

# Message types (lower four bits of the first byte).
SYNC = 0x0
DELAY_REQ = 0x1
PDELAY_REQ = 0x2
PDELAY_RESP = 0x3
FOLLOW_UP = 0x8
DELAY_RESP = 0x9
PDELAY_RESP_FOLLOW_UP = 0xA
ANNOUNCE = 0xB
SIGNALING = 0xC

# Header flags.
FLAG_TIMESCALE = 1 << 3
FLAG_TWO_STEP = 1 << 9
FLAG_UNICAST = 1 << 10

HEADER = struct.Struct(">BBHBBHqI10sHBb")  # 34 bytes
TIMESTAMP = struct.Struct(">HII")  # 10 bytes: seconds (48 bits), nanoseconds
PORT_ID_SIZE = 10
HEADER_SIZE = HEADER.size

# Organisation codes in TLVs.
_ORG_IEEE = b"\x00\x80\xc2"
_ORG_APPLE = b"\x00\x0d\x93"
_TLV_ORG_EXTENSION = 0x0003
_TLV_PATH_TRACE = 0x0008

# Intervals, as iOS and the Apple TV use them (log2 seconds in the header).
SYNC_INTERVAL = 0.125
ANNOUNCE_EVERY = 8  # sync ticks: once a second
_LOG_SYNC = -3
_LOG_ANNOUNCE = 0
_LOG_SIGNALING = -128

PRIORITY1 = 128  # Apple devices announce 248; lower wins, so receivers follow us.
PRIORITY2 = 128
CLOCK_QUALITY = 0x06210000 | 0x436A  # class 6 (GPS), accuracy 100 ns, Apple's variance
TIME_SOURCE_GPS = 0x20


def now_ns() -> int:
    """The PTP clock: the PC's high-resolution counter, in nanoseconds (the same clock as
    `tandem.engine.timeline.now_ns`, which times the captured audio)."""
    return timeline.now_ns()


def new_clock_id() -> int:
    """A random 64-bit clock identity, top bytes set as libairptp does."""
    return secrets.randbits(48) | 0xFFFF000000000000


def signed64(value: int) -> int:
    """AirPlay's plists carry the clock id as a signed 64-bit integer."""
    return value - (1 << 64) if value >= 1 << 63 else value


def timestamp(ns: int) -> bytes:
    seconds, nanos = divmod(ns, 1_000_000_000)
    return TIMESTAMP.pack(seconds >> 32, seconds & 0xFFFFFFFF, nanos)


def port_identity(clock_id: int) -> bytes:
    return clock_id.to_bytes(8, "big") + b"\x80\x05"  # the port number iOS uses


def header(
    msg_type: int,
    length: int,
    clock_id: int,
    sequence: int,
    log_interval: int,
    flags: int,
    control: int = 0,
) -> bytes:
    return HEADER.pack(
        msg_type | 0x10,  # transportSpecific 1, which nqptp and Apple expect
        0x02,  # PTP version 2
        length,
        0,  # domain
        0,
        flags,
        0,  # correctionField
        0,
        port_identity(clock_id),
        sequence & 0xFFFF,
        control,
        log_interval,
    )


def _tlv(tlv_type: int, value: bytes) -> bytes:
    return struct.pack(">HH", tlv_type, len(value)) + value


def announce(clock_id: int, sequence: int) -> bytes:
    body = (
        timestamp(0)  # iOS sends zero here
        + struct.pack(
            ">hBBIBQHB",
            0,  # currentUtcOffset
            0,
            PRIORITY1,
            CLOCK_QUALITY,
            PRIORITY2,
            clock_id,
            0,  # stepsRemoved
            TIME_SOURCE_GPS,
        )
        + _tlv(_TLV_PATH_TRACE, clock_id.to_bytes(8, "big"))
    )
    return (
        header(
            ANNOUNCE,
            HEADER_SIZE + len(body),
            clock_id,
            sequence,
            _LOG_ANNOUNCE,
            FLAG_UNICAST | FLAG_TIMESCALE,
        )
        + body
    )


def signaling(clock_id: int, sequence: int) -> bytes:
    """The Signaling message iOS sends every second. Its Apple TLVs are fixed values whose
    meaning isn't known; libairptp copies them and so do we."""
    unknown = b"\x00\x00\x03\x01"
    tlv1 = _tlv(_TLV_ORG_EXTENSION, (_ORG_APPLE + b"\x00\x00\x01" + unknown).ljust(22, b"\0"))
    tlv2 = _tlv(_TLV_ORG_EXTENSION, (_ORG_APPLE + b"\x00\x00\x05" + unknown).ljust(32, b"\0"))
    body = bytes(PORT_ID_SIZE) + tlv1 + tlv2
    return (
        header(
            SIGNALING,
            HEADER_SIZE + len(body),
            clock_id,
            sequence,
            _LOG_SIGNALING,
            FLAG_UNICAST | FLAG_TIMESCALE,
            control=0x05,
        )
        + body
    )


def sync(clock_id: int, sequence: int) -> bytes:
    """Two-step Sync: the time goes in the Follow_Up."""
    body = timestamp(0)
    return (
        header(
            SYNC,
            HEADER_SIZE + len(body),
            clock_id,
            sequence,
            _LOG_SYNC,
            FLAG_UNICAST | FLAG_TIMESCALE | FLAG_TWO_STEP,
        )
        + body
    )


def follow_up(clock_id: int, sequence: int, sent_ns: int) -> bytes:
    # IEEE 802.1AS Follow_Up information (all zeros: we don't track rate changes), then the
    # Apple TLV that repeats the clock id.
    tlv1 = _tlv(_TLV_ORG_EXTENSION, (_ORG_IEEE + b"\x00\x00\x01").ljust(28, b"\0"))
    tlv2 = _tlv(
        _TLV_ORG_EXTENSION,
        (_ORG_APPLE + b"\x00\x00\x04" + clock_id.to_bytes(8, "big")).ljust(16, b"\0"),
    )
    body = timestamp(sent_ns) + tlv1 + tlv2
    return (
        header(
            FOLLOW_UP,
            HEADER_SIZE + len(body),
            clock_id,
            sequence,
            _LOG_SYNC,
            FLAG_UNICAST | FLAG_TIMESCALE,
        )
        + body
    )


def _response(msg_type: int, clock_id: int, request: bytes, received_ns: int, flags: int) -> bytes:
    sequence = struct.unpack_from(">H", request, 30)[0]
    requester = request[20:30]  # the request's sourcePortIdentity, as sent
    body = timestamp(received_ns) + requester
    return header(msg_type, HEADER_SIZE + len(body), clock_id, sequence, _LOG_SYNC, flags) + body


def delay_resp(clock_id: int, request: bytes, received_ns: int) -> bytes:
    return _response(
        DELAY_RESP,
        clock_id,
        request,
        received_ns,
        FLAG_UNICAST | FLAG_TIMESCALE | FLAG_TWO_STEP,
    )


def pdelay_resp(clock_id: int, request: bytes, received_ns: int) -> bytes:
    return _response(
        PDELAY_RESP,
        clock_id,
        request,
        received_ns,
        FLAG_UNICAST | FLAG_TIMESCALE | FLAG_TWO_STEP,
    )


def pdelay_resp_follow_up(clock_id: int, request: bytes, sent_ns: int) -> bytes:
    return _response(
        PDELAY_RESP_FOLLOW_UP, clock_id, request, sent_ns, FLAG_UNICAST | FLAG_TIMESCALE
    )


@dataclass(frozen=True, slots=True)
class PeerAnnounce:
    """What a receiver said about its own clock (it should defer to ours)."""

    priority1: int
    clock_class: int
    grandmaster: int


def parse_announce(data: bytes) -> PeerAnnounce | None:
    if len(data) < 64:
        return None
    _utc, _res, priority1, quality, _p2, grandmaster, _steps, _src = struct.unpack_from(
        ">hBBIBQHB", data, HEADER_SIZE + TIMESTAMP.size
    )
    return PeerAnnounce(priority1, quality >> 24, grandmaster)


@dataclass(slots=True)
class PeerStats:
    """Counts per receiver, for diagnostics (no addresses leave this object)."""

    delay_requests: int = 0
    pdelay_requests: int = 0
    announces: int = 0
    other: int = 0
    last_announce: PeerAnnounce | None = None
    last_heard_ns: int | None = None


@dataclass(slots=True)
class _Peer:
    users: int = 0
    stats: PeerStats = field(default_factory=PeerStats)


class _Endpoint(asyncio.DatagramProtocol):
    def __init__(self, on_message: Callable[[bytes, tuple[str, int], int], None]) -> None:
        self._on_message = on_message
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._on_message(data, addr, now_ns())  # stamp first: the delay maths needs it

    def error_received(self, exc: Exception) -> None:
        _LOG.debug("PTP socket error: %s", type(exc).__name__)


class PtpError(Exception):
    """The PTP clock can't run (for example, another program holds port 319)."""


class PtpMaster:
    """The sender's PTP clock. Start it once; add each receiver while it streams.

    `add_peer` and `remove_peer` count users, so two streams to one address share it.
    """

    def __init__(
        self,
        *,
        clock_id: int | None = None,
        event_port: int = EVENT_PORT,
        general_port: int = GENERAL_PORT,
        bind_host: str = "0.0.0.0",
    ) -> None:
        self.clock_id = clock_id if clock_id is not None else new_clock_id()
        self._ports = (event_port, general_port)
        self._bind_host = bind_host
        self._event: _Endpoint | None = None
        self._general: _Endpoint | None = None
        self._peers: dict[str, _Peer] = {}
        self._task: asyncio.Task[None] | None = None
        self._sync_seq = 0
        self._announce_seq = 0
        self._signaling_seq = 0
        self._wake = asyncio.Event()

    @property
    def running(self) -> bool:
        return self._task is not None

    async def start(self) -> None:
        if self._task is not None:
            return
        loop = asyncio.get_running_loop()
        try:
            _, event = await loop.create_datagram_endpoint(
                lambda: _Endpoint(self._on_event),
                local_addr=(self._bind_host, self._ports[0]),
            )
            _, general = await loop.create_datagram_endpoint(
                lambda: _Endpoint(self._on_general),
                local_addr=(self._bind_host, self._ports[1]),
            )
        except OSError as exc:
            self._close_sockets()
            raise PtpError(f"can't open the PTP ports: {exc.strerror or exc}") from exc
        self._event, self._general = event, general  # type: ignore[assignment]
        self._task = asyncio.create_task(self._run(), name="ptp-master")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._close_sockets()
        self._peers.clear()

    def _close_sockets(self) -> None:
        for endpoint in (self._event, self._general):
            if endpoint is not None and endpoint.transport is not None:
                endpoint.transport.close()
        self._event = self._general = None

    def add_peer(self, address: str) -> None:
        peer = self._peers.setdefault(address, _Peer())
        peer.users += 1
        self._wake.set()  # announce at once, as libairptp does

    def remove_peer(self, address: str) -> None:
        peer = self._peers.get(address)
        if peer is None:
            return
        peer.users -= 1
        if peer.users <= 0:
            del self._peers[address]

    def stats(self, address: str) -> PeerStats | None:
        peer = self._peers.get(address)
        return peer.stats if peer else None

    @property
    def peer_count(self) -> int:
        return len(self._peers)

    # Sending

    def _send(self, endpoint: _Endpoint | None, port: int, message: bytes) -> None:
        if endpoint is None or endpoint.transport is None:
            return
        for address in list(self._peers):
            try:
                endpoint.transport.sendto(message, (address, port))
            except OSError as exc:  # pragma: no cover - network dependent
                _LOG.debug("PTP send failed: %s", type(exc).__name__)

    def _send_announce(self) -> None:
        self._send(self._general, self._ports[1], announce(self.clock_id, self._announce_seq))
        self._send(self._general, self._ports[1], signaling(self.clock_id, self._signaling_seq))
        self._announce_seq += 1
        self._signaling_seq += 1

    def _send_sync(self) -> None:
        message = sync(self.clock_id, self._sync_seq)
        sent = now_ns()
        self._send(self._event, self._ports[0], message)
        self._send(self._general, self._ports[1], follow_up(self.clock_id, self._sync_seq, sent))
        self._sync_seq += 1

    async def _run(self) -> None:
        tick = 0
        while True:
            if self._peers:
                if self._wake.is_set() or tick % ANNOUNCE_EVERY == 0:
                    self._wake.clear()
                    self._send_announce()
                self._send_sync()
                tick += 1
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), SYNC_INTERVAL)

    # Receiving

    def _peer_stats(self, addr: tuple[str, int], received_ns: int) -> PeerStats | None:
        peer = self._peers.get(addr[0])
        if peer is None:
            return None
        peer.stats.last_heard_ns = received_ns
        return peer.stats

    def _on_event(self, data: bytes, addr: tuple[str, int], received_ns: int) -> None:
        if len(data) < HEADER_SIZE:
            return
        stats = self._peer_stats(addr, received_ns)
        msg_type = data[0] & 0x0F
        if msg_type == DELAY_REQ:
            if stats:
                stats.delay_requests += 1
            self._reply(
                self._general, addr[0], self._ports[1], delay_resp(self.clock_id, data, received_ns)
            )
        elif msg_type == PDELAY_REQ:
            if stats:
                stats.pdelay_requests += 1
            self._reply(
                self._event, addr[0], self._ports[0], pdelay_resp(self.clock_id, data, received_ns)
            )
            self._reply(
                self._general,
                addr[0],
                self._ports[1],
                pdelay_resp_follow_up(self.clock_id, data, now_ns()),
            )
        elif stats:
            stats.other += 1

    def _on_general(self, data: bytes, addr: tuple[str, int], received_ns: int) -> None:
        if len(data) < HEADER_SIZE:
            return
        stats = self._peer_stats(addr, received_ns)
        if stats is None:
            return
        if data[0] & 0x0F == ANNOUNCE:
            stats.announces += 1
            stats.last_announce = parse_announce(data)
        else:
            stats.other += 1

    def _reply(self, endpoint: _Endpoint | None, address: str, port: int, message: bytes) -> None:
        # Reply to anyone who asks, as libairptp does: a receiver may ask before its stream's
        # SETUP reply has named it.
        if endpoint is not None and endpoint.transport is not None:
            try:
                endpoint.transport.sendto(message, (address, port))
            except OSError as exc:  # pragma: no cover - network dependent
                _LOG.debug("PTP reply failed: %s", type(exc).__name__)
