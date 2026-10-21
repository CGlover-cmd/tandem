from __future__ import annotations

import argparse
import asyncio
import io
from collections.abc import Sequence
from pathlib import Path

import pytest

from conftest import make_device
from tandem import cli
from tandem.engine.discovery import Scanner
from tandem.engine.models import Device, DeviceKind, Service
from tandem.engine.redact import Redactor

DEVICES = [
    make_device(),
    make_device(
        id="AA:BB:CC:00:00:02",
        name="Den TV",
        address="192.0.2.20",
        kind=DeviceKind.APPLE_TV,
        model="Apple TV 4K (gen 2)",
        services=frozenset({Service.COMPANION, Service.AIRPLAY}),
    ),
]


def _scanner(devices: Sequence[Device] = DEVICES) -> Scanner:
    async def scan(_timeout: float) -> Sequence[Device]:
        return devices

    return scan


def _run(*argv: str) -> str:
    out = io.StringIO()
    assert cli.main(list(argv), scanner_factory=_scanner, out=out) == 0
    return out.getvalue()


def test_discover_hides_names_and_addresses(tandem_home: Path) -> None:
    output = _run("discover")
    assert "Living Room Speaker" not in output
    assert "Den TV" not in output
    assert "192.0.2" not in output
    assert "<device-1>" in output
    assert "<ip-1>" in output
    assert "Apple TV 4K (gen 2)" in output
    assert "airplay, companion" in output
    assert "2 device(s) found" in output
    assert (tandem_home / "logs" / "tandem.log").exists()


def test_discover_show_private(tandem_home: Path) -> None:
    output = _run("--show-private", "discover")
    assert "Living Room Speaker" in output
    assert "192.0.2.20" in output


def test_discover_with_nothing_found(tandem_home: Path) -> None:
    out = io.StringIO()
    cli.main(["discover"], scanner_factory=lambda: _scanner([]), out=out)
    assert out.getvalue().strip() == "0 device(s) found in 0.0 s"


def test_command_is_required(tandem_home: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main([], scanner_factory=_scanner)


async def test_watch_prints_changes(tandem_home: Path) -> None:
    out = io.StringIO()
    printer = cli._Printer(Redactor(), show_private=False, out=out)  # pyright: ignore[reportPrivateUsage]
    args = argparse.Namespace(interval=60.0, timeout=1.0)
    task = asyncio.create_task(cli._watch(args, _scanner(), printer, Redactor()))  # pyright: ignore[reportPrivateUsage]
    for _ in range(100):
        if out.getvalue().count("+ ") == 2:
            break
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    lines = out.getvalue().splitlines()
    assert lines[0].startswith("Watching")
    assert any(line.startswith("+ <device-") and "homepod" in line for line in lines)
    assert "Den TV" not in out.getvalue()
