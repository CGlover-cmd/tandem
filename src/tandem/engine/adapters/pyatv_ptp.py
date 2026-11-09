"""PTP timing for pyatv's AirPlay 2 audio sender (ADR-0020).

pyatv 0.18 sets every AirPlay 2 stream up with NTP timing, and its sync packets tie each
stream's RTP clock to that stream's own start. Receivers then pick their own delay, which is
why a HomePod plays seconds after a soundbar. With PTP timing the receiver follows Tandem's
clock (`ptp.PtpMaster`), and each sync packet says which RTP sample plays at which PTP time,
so every speaker plays a given moment of audio at the same instant.

Two pyatv internals are wrapped, by name, next to the `open_source` hook in `pyatv_audio`:
- `AirPlayV2._setup_base`: the session SETUP asks for PTP and names Tandem's clock, the reply's
  timing peer becomes a PTP peer, and a SETPEERS tells the receiver who is in the group.
- `ControlClient._sync_task`: sends PTP sync packets (payload type 0xD7) from the stream's
  `PtpTimeline` instead of NTP ones.
A stream only gets these when it was registered with `register` for its receiver's address;
everything else keeps pyatv's own behaviour. A test checks the hook points still exist.

Sync packet layout and SETUP fields follow OwnTone 29.1's AirPlay 2 sender.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import plistlib
import struct
import uuid
from dataclasses import dataclass, field
from typing import Any

from pyatv.auth.hap_channel import setup_channel
from pyatv.protocols.airplay.auth import verify_connection
from pyatv.protocols.airplay.channels import EventChannel
from pyatv.protocols.raop import stream_client
from pyatv.protocols.raop.protocols import airplayv2
from pyatv.support.http import decode_bplist_from_body

from tandem.engine.adapters import ptp

_LOG = logging.getLogger(__name__)

SAMPLE_RATE = 44_100
SYNC_EVERY = 1.0  # seconds, as pyatv and iOS do
# The third field of a PTP sync packet: OwnTone sends the next RTP time less this.
_SYNC_EARLIEST_OFFSET = 11_025
_MASK32 = 0xFFFFFFFF

SETPEERS_CONTENT_TYPE = "/peer-list-changed"


class PtpTimeline:
    """Ties one stream's RTP timestamps to PTP time: sample `rtp0` plays at `t0_ns`.

    Set when the stream starts (`anchor`); after that RTP time runs at exactly 44.1 kHz of
    PTP time, so every packet's play time is known before it is sent."""

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate
        self.rtp0: int | None = None
        self.t0_ns: int | None = None

    @property
    def anchored(self) -> bool:
        return self.t0_ns is not None

    def anchor(self, rtp0: int, t0_ns: int) -> None:
        self.rtp0 = rtp0
        self.t0_ns = t0_ns

    def play_ns(self, frames_from_start: int) -> int:
        """PTP time at which the stream's `frames_from_start`-th frame plays."""
        assert self.t0_ns is not None
        return self.t0_ns + frames_from_start * 1_000_000_000 // self.sample_rate

    def rtp_at(self, t_ns: int) -> int:
        """The RTP timestamp that should be playing at PTP time `t_ns` (modulo 2**32)."""
        assert self.t0_ns is not None
        assert self.rtp0 is not None
        offset = (t_ns - self.t0_ns) * self.sample_rate // 1_000_000_000
        return (self.rtp0 + offset) & _MASK32


@dataclass(slots=True)
class PtpStream:
    """What the hooks need for one receiver's stream."""

    master: ptp.PtpMaster
    group_uuid: str
    lead_ns: int
    """How far ahead of sending a packet plays: room for the network and resends."""
    timeline: PtpTimeline = field(default_factory=PtpTimeline)
    peer_address: str | None = None
    """The receiver's PTP address, from its SETUP reply (set by the hook)."""
    setpeers_status: int | None = None
    setup_error: str | None = None
    sync_packets: int = 0


_streams: dict[str, PtpStream] = {}
_clock_uuid = str(uuid.uuid4()).upper()


def register(address: str, stream: PtpStream) -> None:
    """Use PTP timing for the next stream set up to the receiver at `address`."""
    install_hooks()
    _streams[address] = stream


def unregister(address: str) -> None:
    stream = _streams.pop(address, None)
    if stream is not None and stream.peer_address is not None:
        stream.master.remove_peer(stream.peer_address)
        stream.peer_address = None


def stream_for(address: str) -> PtpStream | None:
    return _streams.get(address)


def supports_ptp(properties: dict[str, str]) -> bool:
    """True if a receiver's AirPlay TXT record advertises PTP (features bit 41)."""
    raw = properties.get("features") or properties.get("ft") or "0x0"
    parts = [int(part, 16) for part in raw.split(",") if part.strip()]
    value = parts[0] | (parts[1] << 32 if len(parts) > 1 else 0)
    return bool(value & (1 << 41))


def choose_peer_address(addresses: list[Any], remote_ip: str) -> str | None:
    """The receiver's PTP address: its RTSP address if listed, else its first IPv4 one."""
    ipv4: list[str] = []
    for item in addresses:
        if not isinstance(item, str):
            continue
        try:
            if ipaddress.ip_address(item.split("%")[0]).version == 4:
                ipv4.append(item)
        except ValueError:
            continue
    if remote_ip in ipv4:
        return remote_ip
    return ipv4[0] if ipv4 else None


def setup_body(base: dict[str, Any], stream: PtpStream, local_ip: str) -> dict[str, Any]:
    """pyatv's session SETUP body, switched from NTP to PTP timing."""
    peer_info = {
        "ID": _clock_uuid,
        "DeviceType": 0,
        "ClockID": ptp.signed64(stream.master.clock_id),
        "SupportsClockPortMatchingOverride": False,
        "Addresses": [local_ip],
    }
    body = {k: v for k, v in base.items() if k not in ("timingPort", "timingProtocol")}
    body.update(
        {
            "timingProtocol": "PTP",
            "timingPeerInfo": peer_info,
            "timingPeerList": [peer_info],
            "groupUUID": stream.group_uuid,
            "groupContainsGroupLeader": False,
        }
    )
    return body


def sync_packet(first: bool, rtp_now: int, now_ns: int, next_rtp: int, clock_id: int) -> bytes:
    """A PTP time announce (RTCP payload type 215): `rtp_now` is playing at PTP `now_ns`."""
    return struct.pack(
        ">BBHIQIQ",
        0x90 if first else 0x80,
        0xD7,
        0x0006,
        rtp_now & _MASK32,
        now_ns,
        (next_rtp - _SYNC_EARLIEST_OFFSET) & _MASK32,
        clock_id,
    )


# pyatv's own session SETUP fields (from its `_setup_base`), with our name.
def _pyatv_base_body() -> dict[str, Any]:
    return {
        "deviceID": "AA:BB:CC:DD:EE:FF",
        "sessionUUID": str(uuid.uuid4()).upper(),
        "isMultiSelectAirPlay": True,
        "macAddress": "AA:BB:CC:DD:EE:FF",
        "model": "iPhone14,3",
        "name": "Tandem",
        "osBuildVersion": "20F66",
        "osName": "iPhone OS",
        "osVersion": "16.5",
        "senderSupportsRelay": False,
        "sourceVersion": "690.7.1",
        "statsCollectionEnabled": False,
    }


_original_setup_base: Any = airplayv2.AirPlayV2._setup_base  # pyright: ignore[reportPrivateUsage]
_original_sync_task: Any = stream_client.ControlClient._sync_task  # pyright: ignore[reportPrivateUsage]


async def _setup_base(self: Any, timing_server_port: int) -> None:
    remote_ip: str = self.rtsp.connection.remote_ip
    stream = _streams.get(remote_ip)
    if stream is None:
        await _original_setup_base(self, timing_server_port)
        return

    local_ip: str = self.rtsp.connection.local_ip
    self._verifier = await verify_connection(self.context.credentials, self.rtsp.connection)
    body = setup_body(_pyatv_base_body(), stream, local_ip)
    resp = decode_bplist_from_body(await self.rtsp.setup(body=body))
    info: dict[str, Any] = resp.get("timingPeerInfo") or {}
    addresses: list[Any] = info.get("Addresses") or []
    peer = choose_peer_address(addresses, remote_ip)
    if peer is None:
        # Some receivers leave the list out; their RTSP address is the best guess.
        peer = remote_ip
    stream.peer_address = peer
    stream.master.add_peer(peer)

    event_port = resp.get("eventPort", 0)
    retries = 5
    transport = None
    while transport is None:
        try:
            transport, _ = await setup_channel(
                EventChannel,
                self._verifier,
                remote_ip,
                event_port,
                airplayv2.EVENTS_SALT,
                airplayv2.EVENTS_READ_INFO,
                airplayv2.EVENTS_WRITE_INFO,
            )
        except ConnectionRefusedError:
            retries -= 1
            if retries == 0:
                raise
            await asyncio.sleep(1.0)
    self.event_channel = transport

    peers = plistlib.dumps([remote_ip, local_ip], fmt=plistlib.FMT_BINARY)
    response = await self.rtsp.exchange(
        "SETPEERS", content_type=SETPEERS_CONTENT_TYPE, body=peers, allow_error=True
    )
    stream.setpeers_status = response.code


async def _sync_task(self: Any, dest: tuple[str, int]) -> None:
    stream = _streams.get(dest[0])
    if stream is None:
        await _original_sync_task(self, dest)
        return
    if self.transport is None:
        raise RuntimeError("socket not connected")

    context = self.context
    timeline = stream.timeline
    # The stream has just been reset and nothing is sent yet: the next packet is its first.
    timeline.anchor(context.rtptime, ptp.now_ns() + stream.lead_ns)
    first = True
    while self.transport is not None:
        now = ptp.now_ns()
        packet = sync_packet(
            first, timeline.rtp_at(now), now, context.rtptime, stream.master.clock_id
        )
        self.transport.sendto(packet, dest)
        stream.sync_packets += 1
        first = False
        await asyncio.sleep(SYNC_EVERY)


def install_hooks() -> None:
    """Wrap pyatv's session setup and sync sender. Safe to call more than once."""
    if airplayv2.AirPlayV2._setup_base is not _setup_base:  # pyright: ignore[reportPrivateUsage]
        airplayv2.AirPlayV2._setup_base = _setup_base  # type: ignore[method-assign]
    if stream_client.ControlClient._sync_task is not _sync_task:  # pyright: ignore[reportPrivateUsage]
        stream_client.ControlClient._sync_task = _sync_task  # type: ignore[method-assign]
