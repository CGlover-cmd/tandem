"""Spike G, part 2: play to several AirPlay 2 speakers on one shared PTP clock.

Throwaway prototype. Tandem acts as the PTP clock the speakers follow (ported from OwnTone's
MIT-licensed libairptp: unicast Announce, two-step Sync/Follow_Up, Signaling, Delay_Resp on
UDP 319/320). Each speaker gets pyatv's AirPlay 2 stream, but with a PTP session SETUP,
SETPEERS, and "time announce" sync packets (payload type 0xD7) that map RTP positions to the
shared clock with the same mapping for every speaker, so they play each sample at the same
moment. `--ntp` streams the same way with pyatv's own NTP timing, for comparison.

It plays a click test (a click every half second over a soft chord) so a listener can hear
whether the speakers line up. Speakers are picked by model; nothing that identifies a device,
address or clock is printed. Counts go to local/music-hw/spike-g.json.

Must run under the installed Tandem's Python on a Private network (firewall), e.g.
    "C:\\Program Files\\Tandem\\python\\pythonw.exe" spikes/run_under_app.py
        spikes/spike_g_ptp.py play --model "JBL Bar 5.1" --model "HomePod Mini" --seconds 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import plistlib
import random
import struct
import sys
import time
import types
import uuid
import wave
from collections import Counter
from pathlib import Path
from typing import Any

import pyatv
from pyatv.auth.hap_channel import setup_channel
from pyatv.const import Protocol
from pyatv.protocols.airplay.auth import extract_credentials, verify_connection
from pyatv.protocols.airplay.channels import EventChannel
from pyatv.protocols.raop.audio_source import open_source
from pyatv.protocols.raop.protocols import StreamContext
from pyatv.protocols.raop.protocols.airplayv2 import (
    EVENTS_READ_INFO,
    EVENTS_SALT,
    EVENTS_WRITE_INFO,
    AirPlayV2,
)
from pyatv.protocols.raop.stream_client import StreamClient
from pyatv.settings import Settings
from pyatv.support.http import decode_bplist_from_body, http_connect
from pyatv.support.rtsp import RtspSession

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "local" / "music-hw"
RATE = 44100
COUNTS: Counter[str] = Counter()

# --- The PTP clock (after OwnTone's libairptp, MIT) ------------------------------------------

EVENT_PORT, GENERAL_PORT = 319, 320
SYNC, DELAY_REQ, FOLLOW_UP, DELAY_RESP, ANNOUNCE, SIGNALING = 0x0, 0x1, 0x8, 0x9, 0xB, 0xC
FLAG_UNICAST_TIMESCALE = 0x0408  # iOS sets 0x0408
FLAG_TWO_STEP = 0x0608
APPLE, IEEE = bytes.fromhex("000d93"), bytes.fromhex("0080c2")


def now_ns() -> int:
    """The clock's time: Windows' high-resolution counter (time.monotonic ticks every ~16 ms
    on Python 3.11)."""
    return time.perf_counter_ns()


def ptp_timestamp(ns: int) -> bytes:
    seconds, nanos = divmod(ns, 1_000_000_000)
    return struct.pack(">HII", seconds >> 32, seconds & 0xFFFFFFFF, nanos)


def org_tlv(org: bytes, subtype: bytes, payload: bytes) -> bytes:
    value = org + subtype + payload
    return struct.pack(">HH", 0x0003, len(value)) + value


class PtpClock:
    def __init__(self) -> None:
        self.clock_id = 0xFFFF000000000000 | random.getrandbits(48)
        self.port_identity = struct.pack(">Q", self.clock_id) + b"\x80\x05"  # as iOS
        self.peers: dict[str, str] = {}  # address -> label
        self._seq: Counter[int] = Counter()
        self._event: asyncio.DatagramTransport | None = None
        self._general: asyncio.DatagramTransport | None = None
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        clock = self

        class Listener(asyncio.DatagramProtocol):
            def __init__(self, port: int) -> None:
                self.port = port

            def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
                clock.received(self.port, data, addr, now_ns())

        self._event, _ = await loop.create_datagram_endpoint(
            lambda: Listener(EVENT_PORT), local_addr=("0.0.0.0", EVENT_PORT)
        )
        self._general, _ = await loop.create_datagram_endpoint(
            lambda: Listener(GENERAL_PORT), local_addr=("0.0.0.0", GENERAL_PORT)
        )
        self._tasks = [
            asyncio.create_task(self._every(1.0, self._announce)),
            asyncio.create_task(self._every(1.0, self._signaling)),
            asyncio.create_task(self._every(0.125, self._sync)),
        ]

    def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for transport in (self._event, self._general):
            if transport is not None:
                transport.close()

    def add_peer(self, address: str, label: str) -> None:
        if address not in self.peers:
            self.peers[address] = label
            self._announce()
            self._signaling()

    def _header(
        self,
        kind: int,
        length: int,
        flags: int,
        control: int,
        interval: int,
        seq: int | None = None,
        correction: int = 0,
    ) -> bytes:
        if seq is None:
            seq = self._seq[kind]
            self._seq[kind] = (seq + 1) & 0xFFFF
        return struct.pack(
            ">BBHBBHqI10sHBb",
            kind | 0x10,  # transportSpecific 1, as nqptp expects
            0x02,
            length,
            0,  # domain
            0,
            flags,
            correction,
            0,
            self.port_identity,
            seq,
            control,
            interval,
        )

    def _send(self, port: int, data: bytes, address: str | None = None) -> None:
        transport = self._event if port == EVENT_PORT else self._general
        if transport is None:
            return
        for peer in [address] if address else list(self.peers):
            transport.sendto(data, (peer, port))

    def _announce(self) -> None:
        body = (
            ptp_timestamp(0)  # iOS sends 0
            + struct.pack(">hBB", 37, 0, 128)  # UTC offset, reserved, priority1
            + bytes.fromhex("0621436a")  # clock class 6, accuracy 0x21, variance 0x436A
            + struct.pack(">B", 128)  # priority2
            + struct.pack(">Q", self.clock_id)
            + struct.pack(">HB", 0, 0x20)  # steps removed, time source (GPS)
            + struct.pack(">HH", 0x0008, 8)
            + struct.pack(">Q", self.clock_id)  # path trace
        )
        data = self._header(ANNOUNCE, 34 + len(body), FLAG_UNICAST_TIMESCALE, 5, 0) + body
        self._send(GENERAL_PORT, data)

    def _signaling(self) -> None:
        body = (
            bytes(10)  # target port identity
            + org_tlv(APPLE, b"\x00\x00\x01", b"\x00\x00\x03\x01" + bytes(12))
            + org_tlv(APPLE, b"\x00\x00\x05", b"\x00\x00\x03\x01" + bytes(22))
        )
        data = self._header(SIGNALING, 34 + len(body), FLAG_UNICAST_TIMESCALE, 5, -128) + body
        self._send(GENERAL_PORT, data)

    def _sync(self) -> None:
        if not self.peers:
            return
        seq = self._seq[SYNC]
        self._seq[SYNC] = (seq + 1) & 0xFFFF
        sync = self._header(SYNC, 44, FLAG_TWO_STEP, 0, -3, seq=seq) + ptp_timestamp(0)
        self._send(EVENT_PORT, sync)
        sent = now_ns()  # two-step: the Follow_Up carries the Sync's time
        body = (
            ptp_timestamp(sent)
            + org_tlv(IEEE, b"\x00\x00\x01", bytes(22))
            + org_tlv(APPLE, b"\x00\x00\x04", struct.pack(">Q", self.clock_id) + bytes(2))
        )
        follow = self._header(FOLLOW_UP, 34 + len(body), FLAG_UNICAST_TIMESCALE, 2, -3, seq=seq)
        self._send(GENERAL_PORT, follow + body)
        COUNTS["ptp.sync"] += 1

    def received(self, port: int, data: bytes, addr: tuple[str, int], at: int) -> None:
        if len(data) < 34:
            return
        kind = data[0] & 0x0F
        label = self.peers.get(addr[0], "other")
        COUNTS[f"ptp.in.{label}.{kind:#x}"] += 1
        if kind == DELAY_REQ:
            correction = struct.unpack_from(">q", data, 8)[0]
            seq = struct.unpack_from(">H", data, 30)[0]
            requester = data[20:30]
            body = ptp_timestamp(at) + requester
            resp = self._header(
                DELAY_RESP,
                34 + len(body),
                FLAG_UNICAST_TIMESCALE,
                3,
                -3,
                seq=seq,
                correction=correction,
            )
            self._send(GENERAL_PORT, resp + body, addr[0])

    async def _every(self, seconds: float, action: Any) -> None:
        while True:
            action()
            await asyncio.sleep(seconds)


# --- AirPlay 2 with PTP timing ------------------------------------------------------------


class Group:
    """What every speaker shares: the clock, a group id and one RTP-to-clock mapping."""

    def __init__(self, clock: PtpClock) -> None:
        self.clock = clock
        self.uuid = str(uuid.uuid4()).upper()
        self.peer_uuid = str(uuid.uuid4()).upper()
        self.anchor_rtp = 0
        self.anchor_ns = 0

    def anchor(self, rtp: int, lead_s: float) -> None:
        """RTP position `rtp` plays `lead_s` seconds from now, on every speaker."""
        self.anchor_rtp = rtp
        self.anchor_ns = now_ns() + int(lead_s * 1e9)

    def time_of(self, rtp: int) -> int:
        return self.anchor_ns + (rtp - self.anchor_rtp) * 1_000_000_000 // RATE


class PtpAirPlayV2(AirPlayV2):
    def __init__(self, context: StreamContext, rtsp: RtspSession, group: Group, label: str):
        super().__init__(context, rtsp)
        self.group = group
        self.label = label

    async def _setup_base(self, timing_server_port: int) -> None:
        self._verifier = await verify_connection(self.context.credentials, self.rtsp.connection)
        local = self.rtsp.connection.local_ip
        peer_info = {
            "ID": self.group.peer_uuid,
            "DeviceType": 0,
            # Signed in the plist (OwnTone: "ClockID in plist is signed").
            "ClockID": struct.unpack(">q", struct.pack(">Q", self.group.clock.clock_id))[0],
            "SupportsClockPortMatchingOverride": False,
            "Addresses": [local],
        }
        resp = decode_bplist_from_body(
            await self.rtsp.setup(
                body={
                    "deviceID": "AA:BB:CC:DD:EE:FF",
                    "macAddress": "AA:BB:CC:DD:EE:FF",
                    "sessionUUID": str(uuid.uuid4()).upper(),
                    "timingProtocol": "PTP",
                    "timingPeerInfo": peer_info,
                    "timingPeerList": [peer_info],
                    "groupUUID": self.group.uuid,
                    "groupContainsGroupLeader": False,
                    "isMultiSelectAirPlay": True,
                    "name": "Tandem",
                    "model": "iPhone14,3",
                    "osName": "iPhone OS",
                    "osVersion": "16.5",
                    "osBuildVersion": "20F66",
                    "sourceVersion": "690.7.1",
                    "senderSupportsRelay": False,
                    "statsCollectionEnabled": False,
                }
            )
        )
        remote = self.rtsp.connection.remote_ip
        addresses = resp.get("timingPeerInfo", {}).get("Addresses", [])
        COUNTS[f"{self.label}.setup.peer_addresses"] = len(addresses)
        self.group.clock.add_peer(remote, self.label)
        event_port = resp.get("eventPort", 0)
        for attempt in range(5):
            try:
                self.event_channel, _ = await setup_channel(
                    EventChannel,
                    self._verifier,
                    remote,
                    event_port,
                    EVENTS_SALT,
                    EVENTS_READ_INFO,
                    EVENTS_WRITE_INFO,
                )
                break
            except ConnectionRefusedError:
                if attempt == 4:
                    raise
                await asyncio.sleep(1.0)

    async def setup(self, timing_server_port: int, control_client_port: int) -> None:
        await super().setup(timing_server_port, control_client_port)
        peers = [self.rtsp.connection.remote_ip, self.rtsp.connection.local_ip]
        resp = await self.rtsp.exchange(
            "SETPEERS",
            uri="/peer-list-changed",
            content_type="application/x-apple-binary-plist",
            body=plistlib.dumps(peers, fmt=plistlib.FMT_BINARY),
            allow_error=True,
        )
        COUNTS[f"{self.label}.setpeers.{resp.code}"] += 1


def ptp_sync_task(group: Group, label: str):  # type: ignore[no-untyped-def]
    async def task(self, dest):  # type: ignore[no-untyped-def]
        first = True
        while self.transport is not None:
            rtp = self.context.rtptime
            packet = struct.pack(
                ">BBHIQIQ",
                0x90 if first else 0x80,
                0xD7,  # "time announce"
                0x0006,
                rtp & 0xFFFFFFFF,
                group.time_of(rtp),
                (rtp - 11025) & 0xFFFFFFFF,
                group.clock.clock_id,
            )
            self.transport.sendto(packet, dest)
            COUNTS[f"{label}.sync_packets"] += 1
            first = False
            await asyncio.sleep(1.0)

    return task


# --- Running it -------------------------------------------------------------------------------


def make_test_file(seconds: float) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"sync-test-{seconds:g}s.wav"
    frames = int(RATE * seconds)
    click = int(RATE * 0.012)
    data = bytearray()
    for n in range(frames):
        t = n / RATE
        fade = min(1.0, t / 0.5, (seconds - t) / 0.5)
        value = (
            0.18 * fade * sum(math.sin(2 * math.pi * f * t) for f in (220.0, 277.18, 329.63)) / 3
        )
        pos = n % (RATE // 2)
        if pos < click:
            value += 0.6 * (1 - pos / click) * math.sin(2 * math.pi * 1760 * t)
        sample = int(max(-1.0, min(1.0, value)) * 32767)
        data += struct.pack("<hh", sample, sample)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(bytes(data))
    return path


async def find(models: list[str]) -> list[Any]:
    confs = await pyatv.scan(asyncio.get_running_loop(), timeout=5)
    chosen: list[Any] = []
    for model in models:
        match = next(
            (
                c
                for c in sorted(confs, key=lambda c: str(c.identifier))
                if model in (str(c.device_info.raw_model), str(c.device_info.model))
                and c.get_service(Protocol.RAOP) is not None
                and c not in chosen
            ),
            None,
        )
        if match is None:
            sys.exit(f"No speaker of model {model!r} found.")
        chosen.append(match)
    return chosen


async def play(models: list[str], seconds: float, use_ntp: bool, lead_s: float) -> None:
    path = make_test_file(seconds)
    confs = await find(models)
    clock = PtpClock()
    group = Group(clock)
    if not use_ntp:
        await clock.start()
    clients: list[StreamClient] = []
    connections = []
    labels = [f"speaker{n + 1}" for n in range(len(confs))]
    try:
        for conf, label in zip(confs, labels, strict=True):
            service = conf.get_service(Protocol.RAOP)
            connection = await http_connect(str(conf.address), service.port)
            connections.append(connection)
            rtsp = RtspSession(connection)
            context = StreamContext()
            context.credentials = extract_credentials(service)
            protocol = (
                AirPlayV2(context, rtsp) if use_ntp else PtpAirPlayV2(context, rtsp, group, label)
            )
            client = StreamClient(rtsp, context, protocol, Settings())
            await client.initialize(service.properties)
            if not use_ntp:
                assert client.control_client is not None
                client.control_client._sync_task = types.MethodType(
                    ptp_sync_task(group, label), client.control_client
                )
            clients.append(client)
        sources = [
            await open_source(
                str(path), c.context.sample_rate, c.context.channels, c.context.bytes_per_channel
            )
            for c in clients
        ]
        # Every stream starts at RTP position = its latency; map that to one moment.
        group.anchor(clients[0].context.latency, lead_s)
        started = time.monotonic()
        results = await asyncio.gather(
            *(c.send_audio(s) for c, s in zip(clients, sources, strict=True)),
            return_exceptions=True,
        )
        for label, result in zip(labels, results, strict=True):
            COUNTS[f"{label}.result.{type(result).__name__ if result else 'ok'}"] += 1
        COUNTS["elapsed_s"] = round(time.monotonic() - started)
    finally:
        clock.stop()
        for connection in connections:
            connection.close()
        report = {
            "mode": "ntp" if use_ntp else "ptp",
            "models": [str(c.device_info.raw_model or c.device_info.model) for c in confs],
            "counts": dict(sorted(COUNTS.items())),
        }
        (OUT / "spike-g.json").write_text(json.dumps(report, indent=2), "utf-8")
        print(json.dumps(report, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("play")
    run.add_argument("--model", action="append", required=True)
    run.add_argument("--seconds", type=float, default=20.0)
    run.add_argument("--ntp", action="store_true", help="pyatv's own NTP timing, to compare")
    run.add_argument("--lead", type=float, default=2.0, help="seconds of buffer before play")
    args = parser.parse_args()
    asyncio.run(play(args.model, args.seconds, args.ntp, args.lead))
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
