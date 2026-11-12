from __future__ import annotations

import asyncio
import socket
import struct

import pytest

from tandem.engine.adapters import ptp

CLOCK = 0xFFFF_1234_5678_9ABC


def _type(message: bytes) -> int:
    return message[0] & 0x0F


def _flags(message: bytes) -> int:
    return struct.unpack_from(">H", message, 6)[0]


def _length(message: bytes) -> int:
    return struct.unpack_from(">H", message, 2)[0]


def _sequence(message: bytes) -> int:
    return struct.unpack_from(">H", message, 30)[0]


def _timestamp_ns(message: bytes, offset: int = ptp.HEADER_SIZE) -> int:
    hi, low, nanos = ptp.TIMESTAMP.unpack_from(message, offset)
    return ((hi << 32) | low) * 1_000_000_000 + nanos


def test_header_matches_libairptp() -> None:
    message = ptp.sync(CLOCK, 7)
    assert len(message) == 44 == _length(message)
    assert message[0] == 0x10  # transportSpecific 1, type Sync
    assert message[1] == 0x02  # PTPv2
    assert message[4] == 0  # domain
    assert message[20:30] == CLOCK.to_bytes(8, "big") + b"\x80\x05"
    assert _sequence(message) == 7
    assert _flags(message) == 0x0608  # unicast, timescale, two-step (as iOS)
    assert struct.unpack_from(">b", message, 33)[0] == -3  # 8 per second
    assert _timestamp_ns(message) == 0


def test_message_sizes_match_libairptp() -> None:
    assert len(ptp.announce(CLOCK, 1)) == 76
    assert len(ptp.signaling(CLOCK, 1)) == 106
    assert len(ptp.follow_up(CLOCK, 1, 5)) == 96
    for message in (ptp.announce(CLOCK, 1), ptp.signaling(CLOCK, 1), ptp.follow_up(CLOCK, 1, 5)):
        assert _length(message) == len(message)


def test_announce_says_we_are_the_better_clock() -> None:
    message = ptp.announce(CLOCK, 3)
    assert _type(message) == ptp.ANNOUNCE
    assert _flags(message) == 0x0408
    parsed = ptp.parse_announce(message)
    assert parsed == ptp.PeerAnnounce(priority1=128, clock_class=6, grandmaster=CLOCK)
    # Path trace TLV repeats the clock id, as iOS does.
    assert message[-12:] == b"\x00\x08\x00\x08" + CLOCK.to_bytes(8, "big")


def test_parse_announce_ignores_short_messages() -> None:
    assert ptp.parse_announce(b"\x1b" * 40) is None


def test_signaling_carries_apple_tlvs() -> None:
    message = ptp.signaling(CLOCK, 2)
    assert _type(message) == ptp.SIGNALING
    assert message[32] == 0x05  # controlField "other"
    assert struct.unpack_from(">b", message, 33)[0] == -128
    tlvs = message[ptp.HEADER_SIZE + ptp.PORT_ID_SIZE :]
    assert tlvs[:4] == b"\x00\x03\x00\x16"  # org extension, 22 bytes
    assert tlvs[4:14] == b"\x00\x0d\x93\x00\x00\x01\x00\x00\x03\x01"
    assert tlvs[26:30] == b"\x00\x03\x00\x20"  # org extension, 32 bytes
    assert tlvs[30:40] == b"\x00\x0d\x93\x00\x00\x05\x00\x00\x03\x01"


def test_follow_up_carries_the_send_time_and_clock_id() -> None:
    sent = 1_234 * 1_000_000_000 + 567_890
    message = ptp.follow_up(CLOCK, 9, sent)
    assert _type(message) == ptp.FOLLOW_UP
    assert _flags(message) == 0x0408
    assert _sequence(message) == 9
    assert _timestamp_ns(message) == sent
    assert message[44:54] == b"\x00\x03\x00\x1c\x00\x80\xc2\x00\x00\x01"
    assert message[76:] == (
        b"\x00\x03\x00\x10\x00\x0d\x93\x00\x00\x04" + CLOCK.to_bytes(8, "big") + b"\0\0"
    )


def test_timestamps_beyond_32_bit_seconds() -> None:
    ns = ((1 << 33) + 5) * 1_000_000_000 + 42
    assert _timestamp_ns(ptp.timestamp(ns), 0) == ns


def _request(msg_type: int, sequence: int) -> bytes:
    requester = b"\x01\x02\x03\x04\x05\x06\x07\x08\x00\x01"
    head = ptp.HEADER.pack(msg_type | 0x10, 2, 44, 0, 0, 0, 0, 0, requester, sequence, 1, 0)
    return head + bytes(10)


def test_delay_resp_answers_the_request() -> None:
    request = _request(ptp.DELAY_REQ, 77)
    message = ptp.delay_resp(CLOCK, request, 99_000_000_123)
    assert len(message) == 54 == _length(message)
    assert _type(message) == ptp.DELAY_RESP
    assert _sequence(message) == 77
    assert _timestamp_ns(message) == 99_000_000_123
    assert message[44:] == request[20:30]


def test_pdelay_messages_answer_the_request() -> None:
    request = _request(ptp.PDELAY_REQ, 5)
    resp = ptp.pdelay_resp(CLOCK, request, 10)
    follow = ptp.pdelay_resp_follow_up(CLOCK, request, 11)
    assert (_type(resp), _type(follow)) == (ptp.PDELAY_RESP, ptp.PDELAY_RESP_FOLLOW_UP)
    assert (_sequence(resp), _sequence(follow)) == (5, 5)
    assert (_timestamp_ns(resp), _timestamp_ns(follow)) == (10, 11)


def test_clock_ids() -> None:
    clock = ptp.new_clock_id()
    assert clock >> 48 == 0xFFFF
    assert ptp.signed64(0xF842885F71750008) == -557733460333756408
    assert ptp.signed64(5) == 5


def test_now_is_nanoseconds_and_rising() -> None:
    first = ptp.now_ns()
    assert ptp.now_ns() >= first


def _free_udp_ports(count: int) -> list[int]:
    sockets = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(count)]
    for sock in sockets:
        sock.bind(("127.0.0.1", 0))
    ports = [sock.getsockname()[1] for sock in sockets]
    for sock in sockets:
        sock.close()
    return ports


async def _until(check: object, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not check():  # type: ignore[operator]
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("timed out")
        await asyncio.sleep(0.01)


async def test_master_talks_to_its_peers() -> None:
    event_port, general_port = _free_udp_ports(2)
    master = ptp.PtpMaster(
        clock_id=CLOCK, event_port=event_port, general_port=general_port, bind_host="127.0.0.1"
    )
    await master.start()
    await master.start()  # second start is a no-op
    try:
        assert master.running
        # The loopback address is its own peer here, so it hears what it sends.
        master.add_peer("127.0.0.1")
        master.add_peer("127.0.0.1")
        assert master.peer_count == 1
        stats = master.stats("127.0.0.1")
        assert stats is not None
        await _until(lambda: stats.announces >= 1 and stats.other >= 2)
        assert stats.last_announce is not None
        assert stats.last_announce.priority1 == ptp.PRIORITY1

        # A receiver's Delay_Req gets a Delay_Resp on the general port.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(_request(ptp.DELAY_REQ, 3), ("127.0.0.1", event_port))
            sock.sendto(_request(ptp.PDELAY_REQ, 4), ("127.0.0.1", event_port))
            sock.sendto(b"short", ("127.0.0.1", event_port))
            sock.sendto(b"short", ("127.0.0.1", general_port))
        await _until(lambda: stats.delay_requests == 1 and stats.pdelay_requests == 1)
        assert stats.last_heard_ns is not None

        master.remove_peer("127.0.0.1")
        assert master.peer_count == 1  # still one user
        master.remove_peer("127.0.0.1")
        master.remove_peer("127.0.0.1")  # unknown now: ignored
        assert master.peer_count == 0
        assert master.stats("127.0.0.1") is None
    finally:
        await master.stop()
    assert not master.running
    await master.stop()  # harmless


async def test_master_ignores_strangers_but_answers_them() -> None:
    event_port, general_port = _free_udp_ports(2)
    master = ptp.PtpMaster(event_port=event_port, general_port=general_port, bind_host="127.0.0.1")
    await master.start()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.sendto(_request(ptp.DELAY_REQ, 1), ("127.0.0.1", event_port))
            sock.sendto(ptp.announce(CLOCK, 1), ("127.0.0.1", general_port))
            sock.sendto(ptp.sync(CLOCK, 1), ("127.0.0.1", event_port))
        await asyncio.sleep(0.05)
        assert master.peer_count == 0
    finally:
        await master.stop()


async def test_busy_port_is_a_ptp_error() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as held:
        held.bind(("127.0.0.1", 0))
        port = held.getsockname()[1]
        master = ptp.PtpMaster(event_port=port, general_port=port, bind_host="127.0.0.1")
        with pytest.raises(ptp.PtpError, match="PTP ports"):
            await master.start()
        assert not master.running
