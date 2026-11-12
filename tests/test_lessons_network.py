"""Speakers by address, the network watch and "Can't find a speaker?" (ADR-0023)."""

from __future__ import annotations

import asyncio
import ipaddress
import json
from pathlib import Path

import pytest

from conftest import FakeBackend, FakeClock, make_device
from tandem.engine import net_check
from tandem.engine.addresses import MAX_ADDRESSES, AddressError, AddressStore, normalize
from tandem.engine.models import Service
from tandem.engine.net_check import Adapter, Finding, PcNetwork, ScanHistory
from tandem.engine.network import NetworkWatch, read_addresses
from tandem.engine.outputs import OutputProblem
from tandem.engine.service import Engine

HIDDEN = make_device(id="AA:BB:CC:00:00:31", name="Garage Speaker", address="192.0.2.31")
SEEN = make_device(id="AA:BB:CC:00:00:32", name="Den Speaker", address="192.0.2.32")


# --- Addresses -------------------------------------------------------------------------


def test_only_home_network_addresses_are_taken() -> None:
    assert normalize(" 192.0.2.31 ") == "192.0.2.31"
    for text, reason in [
        ("speaker", AddressError.INVALID),
        ("192.0.2", AddressError.INVALID),
        ("8.8.8.8", AddressError.NOT_LOCAL),
        ("127.0.0.1", AddressError.NOT_LOCAL),
        ("224.0.0.251", AddressError.NOT_LOCAL),
        ("0.0.0.0", AddressError.NOT_LOCAL),
    ]:
        with pytest.raises(AddressError) as error:
            normalize(text)
        assert error.value.reason == reason, text


def test_addresses_are_saved_and_loaded(tmp_path: Path) -> None:
    path = tmp_path / "addresses.json"
    store = AddressStore(path)
    assert store.add("192.0.2.31") == "192.0.2.31"
    assert store.add("192.0.2.31") == "192.0.2.31"  # once only
    store.add("192.0.2.32")
    assert store.remove("192.0.2.32")
    assert not store.remove("192.0.2.32")
    again = AddressStore(path)
    again.load()
    assert again.addresses() == ["192.0.2.31"]


def test_loading_skips_bad_entries(tmp_path: Path) -> None:
    path = tmp_path / "addresses.json"
    path.write_text(json.dumps(["192.0.2.31", "8.8.8.8", 7, "192.0.2.31", "nope"]), "utf-8")
    store = AddressStore(path)
    store.load()
    assert store.addresses() == ["192.0.2.31"]
    path.write_text("{not json", "utf-8")
    broken = AddressStore(path)
    broken.load()
    assert broken.addresses() == []
    path.write_text('{"a": 1}', "utf-8")
    other = AddressStore(path)
    other.load()
    assert other.addresses() == []
    missing = AddressStore(tmp_path / "missing.json")
    missing.load()
    AddressStore(None).load()
    assert missing.addresses() == []


def test_the_list_has_a_limit() -> None:
    store = AddressStore(None)
    for n in range(MAX_ADDRESSES):
        store.add(f"192.0.2.{n + 1}")
    with pytest.raises(AddressError) as error:
        store.add("192.0.2.200")
    assert error.value.reason == AddressError.TOO_MANY


def test_a_save_that_fails_keeps_the_list(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", "utf-8")
    store = AddressStore(blocker / "addresses.json")  # its folder is a file
    store.add("192.0.2.31")
    assert store.addresses() == ["192.0.2.31"]


async def test_an_added_speaker_is_asked_on_every_scan(tmp_path: Path) -> None:
    backend = FakeBackend([SEEN])
    backend.hidden = [HIDDEN]
    engine = Engine(backend, addresses=AddressStore(tmp_path / "a.json"))
    found = await engine.add_address("192.0.2.31")
    assert [d.id for d in found] == [HIDDEN.id]
    assert engine.addresses.addresses() == ["192.0.2.31"]
    devices = await engine.scan()
    assert {d.id for d in devices} == {SEEN.id, HIDDEN.id}
    assert backend.host_scans[-1] == ["192.0.2.31"]
    assert engine.scans.last_total == 2
    assert engine.redactor.redact("at 192.0.2.31") != "at 192.0.2.31"
    assert engine.remove_address("192.0.2.31")
    await engine.close()


async def test_an_address_where_nothing_answers_is_not_kept() -> None:
    engine = Engine(FakeBackend([]))
    with pytest.raises(AddressError) as error:
        await engine.add_address("192.0.2.99")
    assert error.value.reason == AddressError.NO_ANSWER
    assert engine.addresses.addresses() == []
    await engine.close()


async def test_a_failed_address_scan_still_shows_the_network() -> None:
    backend = FakeBackend([SEEN])
    store = AddressStore(None)
    store.add("192.0.2.31")

    async def broken(hosts: object, timeout: float) -> list[object]:
        raise OSError("no route")

    backend.scan_hosts = broken  # type: ignore[method-assign]
    engine = Engine(backend, addresses=store)
    assert [d.id for d in await engine.scan()] == [SEEN.id]
    backend.scan_failure = OSError("multicast failed")
    # A failed network scan is discovery's to handle.
    with pytest.raises(OSError, match="multicast"):
        await engine.discovery.scan_once()
    await engine.close()


# --- Network watch -----------------------------------------------------------------------


def test_read_addresses_never_returns_loopback() -> None:
    assert all(not a.startswith("127.") for a in read_addresses())


async def test_the_watch_reacts_to_a_new_network_and_to_waking() -> None:
    readings = [frozenset({"192.0.2.5"})] * 2 + [frozenset({"198.51.100.5"})] * 10
    clock = FakeClock()
    steps: asyncio.Queue[None] = asyncio.Queue()
    jumps = iter([3.0, 3.0, 60.0])

    def read() -> frozenset[str]:
        return readings.pop(0) if len(readings) > 1 else readings[0]

    async def sleep(_seconds: float) -> None:
        clock.now += next(jumps, 3.0)
        await steps.put(None)
        await asyncio.sleep(0)

    changes: list[int] = []

    async def on_change() -> None:
        changes.append(len(changes))
        if len(changes) == 2:
            raise RuntimeError("a reaction failed")  # logged, the watch carries on

    watch = NetworkWatch(read=read, clock=clock, sleep=sleep)
    watch.start(on_change)
    watch.start(on_change)  # once only
    assert watch.running
    for _ in range(50):
        await asyncio.sleep(0.01)
        if len(changes) >= 2 and steps.qsize() >= 4:
            break
    await watch.stop()
    assert not watch.running
    assert watch.changes >= 2  # the new address, then the sleep gap
    assert watch.addresses == frozenset({"198.51.100.5"})


async def test_a_failed_read_is_skipped() -> None:
    calls: list[int] = []

    def read() -> frozenset[str]:
        calls.append(1)
        if len(calls) == 2:
            raise OSError("adapter gone")
        return frozenset()

    async def sleep(_seconds: float) -> None:
        await asyncio.sleep(0)

    async def on_change() -> None:
        pass

    watch = NetworkWatch(read=read, sleep=sleep)
    watch.start(on_change)
    for _ in range(50):
        await asyncio.sleep(0.01)
        if len(calls) >= 3:
            break
    await watch.stop()
    assert watch.changes == 0
    assert len(calls) >= 3


async def test_a_network_change_looks_again_at_once() -> None:
    backend = FakeBackend([SEEN])
    engine = Engine(backend)
    engine.discovery.start()
    await engine.network_changed()  # rescans, retries sessions and outputs
    assert engine.discovery.running
    engine.start_network_watch()  # no watch given: nothing happens
    await engine.close()


# --- The network check -------------------------------------------------------------------


class FakeProbe(net_check.Probe):
    def __init__(self, pc: PcNetwork) -> None:
        self.pc = pc

    async def read(self) -> PcNetwork:
        return self.pc


HOME = (ipaddress.IPv4Network("192.0.2.0/24"),)


def test_scan_history_spots_blocked_discovery() -> None:
    scans = ScanHistory()
    scans.record(0, 1)
    scans.record(0, 0)
    assert not scans.blocked()
    scans.record(0, 0)
    assert scans.blocked()
    assert scans.last_total == 0
    scans.record(2, 0)
    assert not scans.blocked()


def test_vpns_are_recognised() -> None:
    assert net_check.is_vpn(Adapter("WireGuard Tunnel"))
    assert net_check.is_vpn(Adapter("Some adapter", tunnel=True))
    assert not net_check.is_vpn(Adapter("Wi-Fi 6 Adapter"))
    assert not net_check.installed_app()  # tests never run from the installed app


def test_parse_reads_the_powershell_answer() -> None:
    output = json.dumps(
        {
            "adapters": {"InterfaceDescription": "Wi-Fi 6 Adapter", "InterfaceType": 71},
            "addresses": [
                {"IPAddress": "192.0.2.5", "PrefixLength": 24},
                {"IPAddress": "bad", "PrefixLength": 24},
                {"IPAddress": "192.0.2.6", "PrefixLength": "24"},
                "junk",
            ],
            "firewall": 1,
        }
    )
    pc = net_check.parse(output, check_firewall=True)
    assert pc.adapters == (Adapter("Wi-Fi 6 Adapter", False),)
    assert pc.networks == HOME
    assert pc.firewall_rule is True
    assert net_check.parse(output, check_firewall=False).firewall_rule is None
    assert net_check.parse('{"firewall": 0}', check_firewall=True).firewall_rule is False
    assert net_check.parse('{"firewall": true}', check_firewall=True).firewall_rule is None
    assert net_check.parse("not json", check_firewall=True) == PcNetwork()
    assert net_check.parse("[1, 2]", check_firewall=True) == PcNetwork()
    assert net_check.parse("", check_firewall=True) == PcNetwork()


def test_outside_counts_speakers_on_other_networks() -> None:
    assert net_check.outside(HOME, ["192.0.2.31", "198.51.100.7", "198.51.100.7", "fe80::1"]) == 1
    assert net_check.outside((), ["198.51.100.7"]) == 0


async def test_a_healthy_pc_has_nothing_to_report() -> None:
    pc = PcNetwork((Adapter("Wi-Fi 6 Adapter"),), HOME, True)
    scans = ScanHistory()
    scans.record(3, 0)
    report = await net_check.run(FakeProbe(pc), scans, speakers=["192.0.2.31"])
    assert report == net_check.Report((), 3, 0)


async def test_every_finding_comes_worst_first() -> None:
    pc = PcNetwork((Adapter("Corporate VPN"),), HOME, False)
    scans = ScanHistory()
    for _ in range(3):
        scans.record(0, 0)
    report = await net_check.run(FakeProbe(pc), scans, speakers=["198.51.100.7"], refused=1)
    assert report.findings == (
        Finding.NO_FIREWALL_RULE,
        Finding.NO_ANSWERS,
        Finding.OTHER_SUBNET,
        Finding.VPN,
        Finding.HOME_ACCESS,
    )
    assert report.other_subnet == 1
    offline = await net_check.run(FakeProbe(PcNetwork((Adapter("Wi-Fi"),))), ScanHistory())
    assert offline.findings == (Finding.OFFLINE,)


async def test_the_engine_check_counts_refusals() -> None:
    backend = FakeBackend([SEEN])
    engine = Engine(backend, network_probe=FakeProbe(PcNetwork((Adapter("Wi-Fi"),), HOME)))
    await engine.scan()
    engine.outputs._failed[SEEN.id] = OutputProblem.ACCESS  # pyright: ignore[reportPrivateUsage]
    report = await engine.check_network()
    assert report.findings == (Finding.HOME_ACCESS,)
    assert report.speakers_seen == 1
    await engine.close()


async def test_the_probe_reads_nothing_off_windows() -> None:
    import sys

    if sys.platform == "win32":
        pytest.skip("reads the real network on Windows")
    assert await net_check.Probe().read() == PcNetwork()


def test_speakers_that_cannot_play_audio_are_not_checked() -> None:
    tv = make_device(services=frozenset({Service.COMPANION}))
    assert not tv.can_play_audio
