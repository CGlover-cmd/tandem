from __future__ import annotations

import asyncio
import plistlib
import struct
from types import SimpleNamespace
from typing import Any

import pytest
from pyatv.protocols.raop import stream_client
from pyatv.protocols.raop.protocols import StreamContext, airplayv2

from tandem.engine.adapters import ptp, pyatv_ptp

CLOCK = 0xFFFF_0000_0000_0042


class _FakeMaster:
    clock_id = CLOCK

    def __init__(self) -> None:
        self.peers: list[str] = []

    def add_peer(self, address: str) -> None:
        self.peers.append(address)

    def remove_peer(self, address: str) -> None:
        self.peers.remove(address)


def _stream(master: _FakeMaster | None = None) -> pyatv_ptp.PtpStream:
    return pyatv_ptp.PtpStream(
        master or _FakeMaster(),  # type: ignore[arg-type]
        "GROUP-UUID",
        2_000_000_000,
    )


@pytest.fixture(autouse=True)
def _clean_registry() -> Any:
    yield
    for address in list(pyatv_ptp._streams):  # pyright: ignore[reportPrivateUsage]
        pyatv_ptp.unregister(address)


def test_hook_points_still_exist() -> None:
    # If pyatv renames these, the hooks would silently do nothing.
    assert callable(getattr(airplayv2.AirPlayV2, "_setup_base", None))
    assert callable(getattr(stream_client.ControlClient, "_sync_task", None))
    for name in ("EVENTS_SALT", "EVENTS_READ_INFO", "EVENTS_WRITE_INFO"):
        assert isinstance(getattr(airplayv2, name), str)
    # The RTP time of a stream's first packet, which the timeline anchors to.
    context = StreamContext()
    context.reset()
    assert context.rtptime == context.latency


def test_install_hooks_is_idempotent() -> None:
    pyatv_ptp.install_hooks()
    pyatv_ptp.install_hooks()
    assert airplayv2.AirPlayV2._setup_base is pyatv_ptp._setup_base  # pyright: ignore[reportPrivateUsage]
    assert stream_client.ControlClient._sync_task is pyatv_ptp._sync_task  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize(
    ("features", "expected"),
    [
        ("0x4A7FCA00,0x3C356BD0", True),  # a HomePod's flags: bit 41 set
        ("0x5A7FFFF7,0x1E", False),  # an older receiver
        ("0x445F8A00,0x1C140", False),
        ("0x0,0x200", True),
    ],
)
def test_supports_ptp(features: str, expected: bool) -> None:
    assert pyatv_ptp.supports_ptp({"features": features}) is expected
    assert pyatv_ptp.supports_ptp({"ft": features}) is expected


def test_supports_ptp_without_features() -> None:
    assert not pyatv_ptp.supports_ptp({})
    assert not pyatv_ptp.supports_ptp({"features": "0x40000"})


def test_choose_peer_address() -> None:
    remote = "192.0.2.10"
    assert pyatv_ptp.choose_peer_address(["fe80::1%en0", "192.0.2.11", remote], remote) == remote
    assert pyatv_ptp.choose_peer_address(["fe80::1", "192.0.2.11"], remote) == "192.0.2.11"
    assert pyatv_ptp.choose_peer_address(["fe80::1", "not an address", 5], remote) is None
    assert pyatv_ptp.choose_peer_address([], remote) is None


def test_setup_body_switches_to_ptp() -> None:
    base = {"deviceID": "AA:BB:CC:DD:EE:FF", "timingPort": 1234, "timingProtocol": "NTP"}
    body = pyatv_ptp.setup_body(base, _stream(), "192.0.2.5")
    assert "timingPort" not in body
    assert body["timingProtocol"] == "PTP"
    assert body["deviceID"] == "AA:BB:CC:DD:EE:FF"
    assert body["groupUUID"] == "GROUP-UUID"
    assert body["groupContainsGroupLeader"] is False
    info = body["timingPeerInfo"]
    assert info["ClockID"] == ptp.signed64(CLOCK)
    assert info["Addresses"] == ["192.0.2.5"]
    assert info["DeviceType"] == 0
    assert body["timingPeerList"] == [info]
    plistlib.dumps(body, fmt=plistlib.FMT_BINARY)  # must serialise (signed 64-bit id)


def test_sync_packet_layout() -> None:
    packet = pyatv_ptp.sync_packet(True, 1000, 123_456_789_000, 20_000, CLOCK)
    assert len(packet) == 28
    head, kind, length, rtp_now, now_ns, earliest, clock = struct.unpack(">BBHIQIQ", packet)
    assert (head, kind, length) == (0x90, 0xD7, 6)
    assert (rtp_now, now_ns, earliest, clock) == (1000, 123_456_789_000, 20_000 - 11_025, CLOCK)
    assert pyatv_ptp.sync_packet(False, -5, 0, 0, CLOCK)[0] == 0x80
    # RTP times wrap at 32 bits.
    assert struct.unpack_from(">I", pyatv_ptp.sync_packet(False, -5, 0, 0, CLOCK), 4)[0] == (
        2**32 - 5
    )


def test_timeline_maps_rtp_to_ptp_time() -> None:
    timeline = pyatv_ptp.PtpTimeline()
    assert not timeline.anchored
    timeline.anchor(66_150, 10_000_000_000)
    assert timeline.anchored
    assert timeline.play_ns(0) == 10_000_000_000
    assert timeline.play_ns(44_100) == 11_000_000_000
    assert timeline.rtp_at(10_000_000_000) == 66_150
    assert timeline.rtp_at(11_000_000_000) == 66_150 + 44_100
    # Before the first packet plays, the "playing now" sample is earlier (wrapping below 0).
    assert timeline.rtp_at(8_000_000_000) == (66_150 - 88_200) % 2**32


def test_register_and_unregister_remove_the_peer() -> None:
    master = _FakeMaster()
    stream = _stream(master)
    pyatv_ptp.register("192.0.2.10", stream)
    assert pyatv_ptp.stream_for("192.0.2.10") is stream
    stream.peer_address = "192.0.2.10"
    master.add_peer("192.0.2.10")
    pyatv_ptp.unregister("192.0.2.10")
    assert master.peers == []
    assert stream.peer_address is None
    assert pyatv_ptp.stream_for("192.0.2.10") is None
    pyatv_ptp.unregister("192.0.2.10")  # harmless


class _FakeRtsp:
    def __init__(self, reply: dict[str, Any]) -> None:
        self.connection = SimpleNamespace(remote_ip="192.0.2.10", local_ip="192.0.2.5")
        self.reply = reply
        self.setup_bodies: list[dict[str, Any]] = []
        self.exchanges: list[tuple[str, str | None, bytes]] = []

    async def setup(self, body: dict[str, Any]) -> Any:
        self.setup_bodies.append(body)
        return SimpleNamespace(body=plistlib.dumps(self.reply, fmt=plistlib.FMT_BINARY))

    async def exchange(self, method: str, **kwargs: Any) -> Any:
        self.exchanges.append((method, kwargs.get("content_type"), kwargs["body"]))
        return SimpleNamespace(code=200)


def _patch_setup(monkeypatch: pytest.MonkeyPatch, refusals: int = 0) -> list[int]:
    async def verify(credentials: Any, connection: Any) -> str:
        return "verifier"

    attempts: list[int] = []

    async def channel(*args: Any) -> tuple[str, None]:
        attempts.append(args[3])
        if len(attempts) <= refusals:
            raise ConnectionRefusedError
        return "event transport", None

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(pyatv_ptp, "verify_connection", verify)
    monkeypatch.setattr(pyatv_ptp, "setup_channel", channel)
    monkeypatch.setattr(pyatv_ptp.asyncio, "sleep", no_sleep)
    return attempts


async def test_setup_hook_asks_for_ptp_and_adds_the_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = _patch_setup(monkeypatch, refusals=1)
    master = _FakeMaster()
    stream = _stream(master)
    pyatv_ptp.register("192.0.2.10", stream)
    rtsp = _FakeRtsp(
        {"eventPort": 5000, "timingPeerInfo": {"Addresses": ["fe80::2", "192.0.2.10"]}}
    )
    protocol = SimpleNamespace(rtsp=rtsp, context=SimpleNamespace(credentials=None))

    await pyatv_ptp._setup_base(protocol, 0)  # pyright: ignore[reportPrivateUsage]

    assert rtsp.setup_bodies[0]["timingProtocol"] == "PTP"
    assert rtsp.setup_bodies[0]["timingPeerInfo"]["Addresses"] == ["192.0.2.5"]
    assert master.peers == ["192.0.2.10"]
    assert stream.peer_address == "192.0.2.10"
    assert protocol.event_channel == "event transport"  # type: ignore[attr-defined]
    assert attempts == [5000, 5000]  # one refusal, then connected
    method, content_type, body = rtsp.exchanges[0]
    assert (method, content_type) == ("SETPEERS", "/peer-list-changed")
    assert plistlib.loads(body) == ["192.0.2.10", "192.0.2.5"]
    assert stream.setpeers_status == 200


async def test_setup_hook_falls_back_to_the_rtsp_address(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_setup(monkeypatch)
    master = _FakeMaster()
    pyatv_ptp.register("192.0.2.10", _stream(master))
    rtsp = _FakeRtsp({"eventPort": 5000})
    protocol = SimpleNamespace(rtsp=rtsp, context=SimpleNamespace(credentials=None))
    await pyatv_ptp._setup_base(protocol, 0)  # pyright: ignore[reportPrivateUsage]
    assert master.peers == ["192.0.2.10"]


async def test_setup_hook_gives_up_when_events_never_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_setup(monkeypatch, refusals=99)
    pyatv_ptp.register("192.0.2.10", _stream())
    rtsp = _FakeRtsp({"eventPort": 5000})
    protocol = SimpleNamespace(rtsp=rtsp, context=SimpleNamespace(credentials=None))
    with pytest.raises(ConnectionRefusedError):
        await pyatv_ptp._setup_base(protocol, 0)  # pyright: ignore[reportPrivateUsage]


async def test_unregistered_receivers_keep_pyatvs_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    async def original(self: Any, port: int) -> None:
        calls.append(port)

    monkeypatch.setattr(pyatv_ptp, "_original_setup_base", original)
    protocol = SimpleNamespace(rtsp=_FakeRtsp({}))
    await pyatv_ptp._setup_base(protocol, 7)  # pyright: ignore[reportPrivateUsage]
    assert calls == [7]


async def test_unregistered_receivers_keep_pyatvs_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []

    async def original(self: Any, dest: tuple[str, int]) -> None:
        calls.append(dest)

    monkeypatch.setattr(pyatv_ptp, "_original_sync_task", original)
    await pyatv_ptp._sync_task(SimpleNamespace(), ("192.0.2.99", 6000))  # pyright: ignore[reportPrivateUsage]
    assert calls == [("192.0.2.99", 6000)]


class _FakeTransport:
    def __init__(self, owner: Any, stop_after: int) -> None:
        self.owner = owner
        self.stop_after = stop_after
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, data: bytes, dest: tuple[str, int]) -> None:
        self.sent.append((data, dest))
        if len(self.sent) >= self.stop_after:
            self.owner.transport = None


async def test_sync_hook_anchors_and_sends_ptp_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    times = iter([50_000_000_000, 50_000_000_000, 51_000_000_000])
    monkeypatch.setattr(pyatv_ptp.ptp, "now_ns", lambda: next(times))

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(pyatv_ptp.asyncio, "sleep", no_sleep)
    stream = _stream()
    pyatv_ptp.register("192.0.2.10", stream)
    context = StreamContext()
    context.reset()
    client = SimpleNamespace(context=context)
    client.transport = _FakeTransport(client, stop_after=2)
    sent = client.transport.sent

    await pyatv_ptp._sync_task(client, ("192.0.2.10", 6000))  # pyright: ignore[reportPrivateUsage]

    rtp0 = context.latency
    assert stream.timeline.rtp0 == rtp0
    assert stream.timeline.t0_ns == 52_000_000_000  # now + 2 s lead
    assert stream.sync_packets == 2
    first = struct.unpack(">BBHIQIQ", sent[0][0])
    second = struct.unpack(">BBHIQIQ", sent[1][0])
    assert first[0] == 0x90
    assert second[0] == 0x80
    # At send time the first packet is still 2 s (88200 samples) away.
    assert first[3] == (rtp0 - 88_200) % 2**32
    assert second[3] == (rtp0 - 44_100) % 2**32
    assert first[4] == 50_000_000_000
    assert second[4] == 51_000_000_000
    assert first[6] == CLOCK
    assert sent[0][1] == ("192.0.2.10", 6000)


async def test_sync_hook_needs_a_socket() -> None:
    pyatv_ptp.register("192.0.2.10", _stream())
    client = SimpleNamespace(context=StreamContext(), transport=None)
    with pytest.raises(RuntimeError, match="socket"):
        await pyatv_ptp._sync_task(client, ("192.0.2.10", 6000))  # pyright: ignore[reportPrivateUsage]


async def test_real_master_with_hooks_end_to_end_clock_id() -> None:
    # The stream carries the real master's clock id into the SETUP body.
    master = ptp.PtpMaster(clock_id=CLOCK)
    stream = pyatv_ptp.PtpStream(master, "G", 1)
    body = pyatv_ptp.setup_body({}, stream, "192.0.2.5")
    assert body["timingPeerInfo"]["ClockID"] == ptp.signed64(CLOCK)
    await asyncio.sleep(0)
