from __future__ import annotations

import argparse
import asyncio
import io
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from conftest import FakeBackend, make_device
from tandem import cli
from tandem.engine.models import DeviceKind, Service
from tandem.engine.redact import Redactor
from tandem.engine.service import Engine

SPEAKER = make_device()
SPEAKER_2 = make_device(id="AA:BB:CC:00:00:03", name="Porch Speaker", address="192.0.2.30")
TV = make_device(
    id="AA:BB:CC:00:00:02",
    name="Den TV",
    address="192.0.2.20",
    kind=DeviceKind.APPLE_TV,
    model="Apple TV 4K (gen 2)",
    services=frozenset({Service.COMPANION, Service.AIRPLAY, Service.MRP}),
    needs_pairing=frozenset({Service.COMPANION, Service.AIRPLAY, Service.MRP}),
)


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend([SPEAKER, TV])


def _answer(pin: str) -> Callable[[str], str]:
    def answer(_prompt: str) -> str:
        return pin

    return answer


def _run(backend: FakeBackend, *argv: str, code: int = 0) -> str:
    out = io.StringIO()
    assert cli.main(list(argv), backend_factory=lambda: backend, out=out) == code
    return out.getvalue()


def test_discover_hides_names_and_addresses(tandem_home: Path, backend: FakeBackend) -> None:
    output = _run(backend, "discover")
    assert "Living Room Speaker" not in output
    assert "Den TV" not in output
    assert "192.0.2" not in output
    assert "<device-1>" in output
    assert "<ip-1>" in output
    assert "Apple TV 4K (gen 2)" in output
    assert "NEEDS PAIRING" in output
    assert "airplay, companion, mrp" in output
    assert "2 device(s) found" in output
    assert backend.loaded
    assert (tandem_home / "logs" / "tandem.log").exists()


def test_discover_show_private(tandem_home: Path, backend: FakeBackend) -> None:
    output = _run(backend, "--show-private", "discover")
    assert "Living Room Speaker" in output
    assert "192.0.2.20" in output


def test_discover_with_nothing_found(tandem_home: Path) -> None:
    output = _run(FakeBackend([]), "discover")
    assert output.strip() == "0 device(s) found in 0.0 s"


def test_command_is_required(tandem_home: Path, backend: FakeBackend) -> None:
    with pytest.raises(SystemExit):
        cli.main([], backend_factory=lambda: backend)


def test_pair_every_needed_service_from_the_prompt(
    tandem_home: Path, backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("builtins.input", _answer("1234"))
    output = _run(backend, "pair", "apple_tv")
    assert "Pairing companion with <device-" in output
    assert "Pairing airplay with" in output
    assert output.count("Paired") == 2
    assert "Pairing mrp" not in output  # the AirPlay pairing covered it
    assert backend.credentials == {(TV.id, Service.COMPANION), (TV.id, Service.AIRPLAY)}
    assert "Den TV" not in output


def test_pair_one_service(
    tandem_home: Path, backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("builtins.input", _answer("1234"))
    _run(backend, "pair", "Apple TV", "--service", "airplay")
    assert backend.credentials == {(TV.id, Service.AIRPLAY)}


def test_pair_wrong_pin_fails(
    tandem_home: Path, backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("builtins.input", _answer("0000"))
    output = _run(backend, "pair", "apple_tv", "--service", "companion", code=1)
    assert "Pairing failed (NotPaired)" in output
    assert backend.saves == 0


def test_pair_device_that_needs_none(tandem_home: Path, backend: FakeBackend) -> None:
    assert "needs no pairing" in _run(backend, "pair", "homepod")


def test_pair_ambiguous_target_lists_choices(tandem_home: Path) -> None:
    backend = FakeBackend([SPEAKER, SPEAKER_2])
    output = _run(backend, "pair", "homepod", code=1)
    assert "2 devices match" in output
    assert "  1. <device-" in output
    assert "  2. <device-" in output
    assert "Porch Speaker" not in output


def test_no_match_and_bad_nth(tandem_home: Path, backend: FakeBackend) -> None:
    assert "No device matches" in _run(backend, "pair", "toaster", code=1)
    assert "--nth must be between 1 and 1" in _run(backend, "pair", "homepod", "--nth", "5", code=1)


async def test_pin_file_is_read_and_deleted(tmp_path: Path) -> None:
    pin_file = tmp_path / "pin.txt"
    args = argparse.Namespace(pin_file=pin_file)
    provider = cli._pin_provider(args)  # pyright: ignore[reportPrivateUsage]
    poll = cli._PIN_POLL  # pyright: ignore[reportPrivateUsage]
    task: asyncio.Future[str] = asyncio.ensure_future(provider())
    await asyncio.sleep(0.05)
    pin_file.write_text("4821\n", encoding="utf-8")
    assert await asyncio.wait_for(task, poll * 4) == "4821"
    assert not pin_file.exists()


def test_pair_with_pin_file_announces_where_to_type(
    tandem_home: Path, backend: FakeBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin_file = tmp_path / "pin.txt"
    pin_file.write_text("9999", encoding="utf-8")  # stale PIN from an earlier run: ignored

    async def provide() -> str:
        return "1234"

    def provider(_args: argparse.Namespace) -> Callable[[], Awaitable[str]]:
        return provide

    monkeypatch.setattr(cli, "_pin_provider", provider)
    output = _run(
        backend, "pair", "apple_tv", "--service", "companion", "--pin-file", str(pin_file)
    )
    assert "Waiting for it in" in output
    assert not pin_file.exists()
    assert backend.credentials == {(TV.id, Service.COMPANION)}


def test_connect_all_then_disconnect(tandem_home: Path, backend: FakeBackend) -> None:
    output = _run(backend, "connect", "all", "--hold", "0")
    assert "Connected to and disconnected from 2 of 2 device(s)" in output
    assert output.count(": connected") == 2
    assert output.count(": disconnected") == 2
    assert all(links[0].closed for links in backend.links.values())
    assert "192.0.2" not in output


def test_connect_reports_failures(tandem_home: Path, backend: FakeBackend) -> None:
    backend.connect_failures[SPEAKER.id] = [OSError(), OSError(), OSError()]
    output = _run(backend, "connect", "homepod", "--hold", "0", code=1)
    assert "retrying in" in output
    assert "gave up (OSError)" in output
    assert "Connected to and disconnected from 0 of 1 device(s)" in output


def test_forget(tandem_home: Path, backend: FakeBackend) -> None:
    backend.credentials.add((TV.id, Service.COMPANION))
    assert "Forgot <device-" in _run(backend, "forget", "apple_tv")
    assert "No stored credentials" in _run(backend, "forget", "apple_tv")


async def test_watch_prints_changes(tandem_home: Path, backend: FakeBackend) -> None:
    out = io.StringIO()
    redactor = Redactor()
    printer = cli._Printer(redactor, show_private=False, out=out)  # pyright: ignore[reportPrivateUsage]
    engine = Engine(backend, redactor=redactor, discovery_interval=60.0)
    args = argparse.Namespace(interval=60.0, timeout=1.0)
    task = asyncio.create_task(cli._watch(engine, args, printer))  # pyright: ignore[reportPrivateUsage]
    for _ in range(100):
        if out.getvalue().count("+ ") == 2:
            break
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await engine.close()
    lines = out.getvalue().splitlines()
    assert lines[0].startswith("Watching")
    assert any(line.startswith("+ <device-") and "homepod" in line for line in lines)
    assert "Den TV" not in out.getvalue()


def test_pair_skips_airplay_audio_when_airplay_is_offered(
    tandem_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tv = make_device(
        id="AA:BB:CC:00:00:04",
        kind=DeviceKind.APPLE_TV,
        model="Apple TV 4K (gen 2)",
        services=frozenset({Service.AIRPLAY, Service.RAOP}),
        needs_pairing=frozenset({Service.AIRPLAY, Service.RAOP}),
    )
    backend = FakeBackend([tv])
    monkeypatch.setattr("builtins.input", _answer("1234"))
    output = _run(backend, "pair", "apple_tv")
    assert "Pairing airplay" in output
    assert "Pairing raop" not in output
