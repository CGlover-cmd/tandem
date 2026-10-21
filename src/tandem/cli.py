"""Developer command-line tool: ``python -m tandem <command>``.

Device names and addresses are replaced with placeholders such as ``<device-1>`` unless
``--show-private`` is given, so the output is safe to paste into an issue (docs/PRIVACY.md).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from collections.abc import Callable, Sequence
from typing import TextIO

from tandem import __version__
from tandem.engine import paths
from tandem.engine.discovery import Discovery, Scanner
from tandem.engine.events import EventBus
from tandem.engine.logs import configure_logging
from tandem.engine.models import Device
from tandem.engine.redact import Redactor
from tandem.engine.registry import DeviceAdded, DeviceEvent, DeviceLost, DeviceRegistry

ScannerFactory = Callable[[], Scanner]


def _default_scanner() -> Scanner:
    from tandem.engine.adapters import pyatv_adapter  # imported late: keeps --help fast

    return pyatv_adapter.scanner()


class _Printer:
    def __init__(self, redactor: Redactor, show_private: bool, out: TextIO) -> None:
        self._redactor = redactor
        self._show_private = show_private
        self._out = out

    def name(self, device: Device) -> str:
        return device.name if self._show_private else self._redactor.add(device.name, "device")

    def address(self, device: Device) -> str:
        return (
            device.address
            if self._show_private
            else self._redactor.placeholder(device.address, "ip")
        )

    def line(self, text: str = "") -> None:
        print(text, file=self._out, flush=True)

    def table(self, devices: Sequence[Device]) -> None:
        rows = [
            (
                self.name(d),
                d.kind.value,
                d.model,
                ", ".join(sorted(s.value for s in d.services)),
                self.address(d),
            )
            for d in devices
        ]
        header = ("NAME", "KIND", "MODEL", "SERVICES", "ADDRESS")
        widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]
        for row in [header, *rows]:
            self.line("  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tandem", description="Tandem developer tool")
    parser.add_argument("--version", action="version", version=f"tandem {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="show debug logs")
    parser.add_argument(
        "--show-private",
        action="store_true",
        help="show real device names and addresses (don't paste this output publicly)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    discover = commands.add_parser("discover", help="scan the network once and list devices")
    discover.add_argument("--timeout", type=float, default=3.0, help="scan time in seconds")

    watch = commands.add_parser("watch", help="keep scanning and print devices as they change")
    watch.add_argument("--interval", type=float, default=10.0, help="seconds between scans")
    watch.add_argument("--timeout", type=float, default=3.0, help="scan time in seconds")
    return parser


async def _discover(
    args: argparse.Namespace, scanner: Scanner, printer: _Printer, redactor: Redactor
) -> int:
    registry = DeviceRegistry(EventBus(), redactor)
    discovery = Discovery(registry, scanner, scan_timeout=args.timeout)
    started = time.perf_counter()
    await discovery.scan_once()
    elapsed = time.perf_counter() - started
    devices = registry.devices()
    if devices:
        printer.table(devices)
    printer.line(f"{len(devices)} device(s) found in {elapsed:.1f} s")
    return 0


async def _watch(
    args: argparse.Namespace, scanner: Scanner, printer: _Printer, redactor: Redactor
) -> int:
    bus = EventBus()
    registry = DeviceRegistry(bus, redactor)
    discovery = Discovery(registry, scanner, interval=args.interval, scan_timeout=args.timeout)

    def on_event(event: DeviceEvent) -> None:
        mark = (
            "+" if isinstance(event, DeviceAdded) else "-" if isinstance(event, DeviceLost) else "~"
        )
        device = event.device
        printer.line(f"{mark} {printer.name(device)}  {device.kind.value}  {device.model}")

    bus.subscribe(DeviceEvent, on_event)
    printer.line("Watching for devices. Press Ctrl+C to stop.")
    discovery.start()
    try:
        await asyncio.Event().wait()
    finally:
        await discovery.stop()
    return 0  # pragma: no cover - only reached by cancellation


def main(
    argv: Sequence[str] | None = None,
    *,
    scanner_factory: ScannerFactory = _default_scanner,
    out: TextIO | None = None,
) -> int:
    args = _parser().parse_args(argv)
    redactor = Redactor()
    configure_logging(
        redactor,
        log_dir=paths.log_dir(),
        level=logging.DEBUG if args.verbose else logging.INFO,
        console_level=logging.DEBUG if args.verbose else logging.WARNING,
    )
    printer = _Printer(redactor, args.show_private, out or sys.stdout)
    command = {"discover": _discover, "watch": _watch}[args.command]
    try:
        return asyncio.run(command(args, scanner_factory(), printer, redactor))
    except KeyboardInterrupt:
        return 130
