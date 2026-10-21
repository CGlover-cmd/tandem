"""Developer command-line tool: ``python -m tandem <command>``.

Device names and addresses are replaced with placeholders such as ``<device-1>`` unless
``--show-private`` is given, so the output is safe to paste into an issue (docs/PRIVACY.md).

Commands that act on a device take a TARGET: ``all``, a kind (``apple_tv``, ``homepod``,
``receiver``), part of a model name (``"HomePod Mini"``) or a device's exact name.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from pathlib import Path
from typing import TextIO

from tandem import __version__
from tandem.engine import paths
from tandem.engine.audio import AudioStreamChanged, StreamState
from tandem.engine.control import (
    ControlError,
    ControlsAvailable,
    ControlStatus,
    DeviceControls,
    KeyAction,
    MediaCommand,
    NowPlaying,
    NowPlayingChanged,
    RemoteKey,
    VolumeControl,
)
from tandem.engine.logs import configure_logging
from tandem.engine.models import Device, Service
from tandem.engine.pairing import PairingError, PairingState, PairingStateChanged, PinProvider
from tandem.engine.redact import Redactor
from tandem.engine.registry import DeviceAdded, DeviceEvent, DeviceLost
from tandem.engine.service import Backend, Engine
from tandem.engine.session import ConnectionFailedError, ConnectionState, ConnectionStateChanged
from tandem.engine.settings import SettingsStore

BackendFactory = Callable[[], Backend]

# Order to pair in when a device needs several services (Companion first, as in Spike A).
_PAIRING_ORDER = [Service.COMPANION, Service.AIRPLAY, Service.RAOP, Service.MRP, Service.DMAP]
_PIN_POLL = 0.5


def _default_backend() -> Backend:
    # Imported late: keeps --help fast and pyatv out of the import path until needed.
    from tandem.engine.adapters.credential_vault import CredentialVault
    from tandem.engine.adapters.pyatv_adapter import PyatvBackend

    return PyatvBackend(CredentialVault(paths.credentials_file()))


class _Printer:
    def __init__(self, redactor: Redactor, show_private: bool, out: TextIO) -> None:
        self._redactor = redactor
        self._show_private = show_private
        self._out = out

    def name(self, device: Device) -> str:
        return device.name if self._show_private else self._redactor.add(device.name, "device")

    def label(self, device: Device) -> str:
        return f"{self.name(device)} ({device.model})"

    def address(self, device: Device) -> str:
        if self._show_private:
            return device.address
        return self._redactor.placeholder(device.address, "ip")

    def text(self, text: str) -> str:
        return text if self._show_private else self._redactor.redact(text)

    def line(self, text: str = "") -> None:
        print(text, file=self._out, flush=True)

    def table(self, devices: Sequence[Device]) -> None:
        def services(items: frozenset[Service]) -> str:
            return ", ".join(sorted(s.value for s in items)) or "-"

        rows = [
            (
                self.name(d),
                d.kind.value,
                d.model,
                services(d.services),
                services(d.paired),
                services(d.needs_pairing),
                self.address(d),
            )
            for d in devices
        ]
        header = ("NAME", "KIND", "MODEL", "SERVICES", "PAIRED", "NEEDS PAIRING", "ADDRESS")
        widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]
        for row in [header, *rows]:
            cells = (cell.ljust(width) for cell, width in zip(row, widths, strict=True))
            self.line("  ".join(cells).rstrip())


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

    def add_scan_timeout(command: argparse.ArgumentParser, default: float) -> None:
        command.add_argument("--timeout", type=float, default=default, help="scan time, seconds")

    def add_target(command: argparse.ArgumentParser) -> None:
        command.add_argument("target", help="all, a kind, part of a model name, or a name")
        command.add_argument(
            "--nth", type=int, help="pick the Nth match when several devices match"
        )

    discover = commands.add_parser("discover", help="scan the network once and list devices")
    add_scan_timeout(discover, 3.0)

    watch = commands.add_parser("watch", help="keep scanning and print devices as they change")
    watch.add_argument("--interval", type=float, default=10.0, help="seconds between scans")
    add_scan_timeout(watch, 3.0)

    pair = commands.add_parser("pair", help="pair with a device (enter the PIN it shows)")
    add_target(pair)
    add_scan_timeout(pair, 5.0)
    pair.add_argument(
        "--service",
        action="append",
        choices=[s.value for s in Service],
        help="service to pair (repeatable); default: every service that needs pairing",
    )
    pair.add_argument("--pin-file", type=Path, help="read the PIN from this file, not the prompt")
    pair.add_argument("--pin-timeout", type=float, default=180.0, help="seconds to wait for a PIN")

    connect = commands.add_parser("connect", help="connect, stay connected a while, disconnect")
    add_target(connect)
    add_scan_timeout(connect, 5.0)
    connect.add_argument("--hold", type=float, default=3.0, help="seconds to stay connected")
    connect.add_argument(
        "--keep", action="store_true", help="stay connected (and reconnect) until Ctrl+C"
    )
    connect.add_argument(
        "--connect-timeout", type=float, default=30.0, help="seconds to wait for each connection"
    )

    forget = commands.add_parser("forget", help="delete a device's stored pairing credentials")
    add_target(forget)
    add_scan_timeout(forget, 5.0)

    diagnose = commands.add_parser(
        "diagnose", help="write a redacted diagnostics bundle to attach to a bug report"
    )
    add_scan_timeout(diagnose, 5.0)
    diagnose.add_argument(
        "--out", type=Path, help="folder for the bundle (default: the app's diagnostics folder)"
    )
    _add_control_parsers(commands, add_target, add_scan_timeout)
    return parser


def _add_control_parsers(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],  # pyright: ignore[reportPrivateUsage]
    add_target: Callable[[argparse.ArgumentParser], None],
    add_scan_timeout: Callable[[argparse.ArgumentParser, float], None],
) -> None:
    def control(name: str, help_text: str) -> argparse.ArgumentParser:
        command = commands.add_parser(name, help=help_text)
        add_target(command)
        add_scan_timeout(command, 5.0)
        return command

    control("controls", "connect and list what the device can do right now")
    remote = control("remote", "press remote keys")
    remote.add_argument("keys", nargs="+", choices=[k.value for k in RemoteKey], metavar="KEY")
    remote.add_argument(
        "--action",
        choices=[a.value for a in KeyAction],
        default="tap",
        help="tap, double_tap, hold",
    )
    remote.add_argument("--gap", type=float, default=0.3, help="seconds between key presses")
    media = control("media", "play, pause, skip and so on")
    media.add_argument("media_command", choices=[c.value for c in MediaCommand], metavar="COMMAND")
    playing = control("playing", "show what is playing")
    playing.add_argument("--watch", type=float, default=0.0, help="keep printing for N seconds")
    power = control("power", "show or change power state")
    power.add_argument("state", nargs="?", choices=["on", "off"])
    volume = control("volume", "show the volume, step it, or set a level")
    volume.add_argument("change", nargs="?", help="up, down, or a level from 0 to 100")
    control("apps", "list installed apps")
    launch = control("launch", "open an app by its id (see `apps`)")
    launch.add_argument("app_id")
    type_text = control("type", "replace the text in the focused text field")
    type_text.add_argument("text")

    stream = commands.add_parser("stream", help="stream this PC's audio to a device")
    add_target(stream)
    add_scan_timeout(stream, 5.0)
    stream.add_argument(
        "--seconds", type=float, default=0.0, help="stop after N seconds (default: until Ctrl+C)"
    )
    stream.add_argument("--volume", type=float, help="device volume to start at, 0 to 100")
    stream.add_argument("--stats-every", type=float, default=10.0, help="seconds between stats")


def _matches(devices: Sequence[Device], target: str) -> list[Device]:
    if target.casefold() == "all":
        return list(devices)
    wanted = target.casefold()
    return [
        d
        for d in devices
        if wanted in (d.kind.value, d.name.casefold()) or wanted in d.model.casefold()
    ]


def _select(
    devices: Sequence[Device], args: argparse.Namespace, printer: _Printer, *, single: bool
) -> list[Device]:
    """Devices the TARGET (and --nth) pick, or [] after printing why."""
    matches = _matches(devices, args.target)
    if args.nth is not None:
        if not 1 <= args.nth <= len(matches):
            printer.line(f"--nth must be between 1 and {len(matches)}")
            return []
        return [matches[args.nth - 1]]
    if not matches:
        printer.line("No device matches that target. Run `discover` to see what's on the network.")
    elif single and len(matches) > 1:
        printer.line(f"{len(matches)} devices match. Pick one with --nth:")
        for index, device in enumerate(matches, start=1):
            printer.line(f"  {index}. {printer.label(device)}")
        return []
    return matches


def _pin_provider(args: argparse.Namespace) -> PinProvider:
    pin_file: Path | None = args.pin_file
    if pin_file is None:

        async def prompt() -> str:
            return await asyncio.to_thread(input, "PIN shown on the device: ")

        return prompt

    def take() -> str | None:
        try:
            text = pin_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        pin_file.unlink(missing_ok=True)
        return text

    async def from_file() -> str:
        # Polling is fine here: a person is typing the PIN into a file by hand.
        while (pin := await asyncio.to_thread(take)) is None:  # noqa: ASYNC110
            await asyncio.sleep(_PIN_POLL)
        return pin

    return from_file


async def _discover(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    started = time.perf_counter()
    devices = await engine.scan()
    elapsed = time.perf_counter() - started
    if devices:
        printer.table(devices)
    printer.line(f"{len(devices)} device(s) found in {elapsed:.1f} s")
    return 0


async def _watch(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    def on_event(event: DeviceEvent) -> None:
        mark = (
            "+" if isinstance(event, DeviceAdded) else "-" if isinstance(event, DeviceLost) else "~"
        )
        device = event.device
        printer.line(f"{mark} {printer.name(device)}  {device.kind.value}  {device.model}")

    engine.bus.subscribe(DeviceEvent, on_event)
    printer.line("Watching for devices. Press Ctrl+C to stop.")
    engine.discovery.start()
    await asyncio.Event().wait()
    return 0  # pragma: no cover - only reached by cancellation


async def _pair(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    selected = _select(await engine.scan(), args, printer, single=True)
    if not selected:
        return 1
    device = selected[0]
    if args.service:
        wanted = {Service(value) for value in args.service}
    else:
        wanted = set(device.needs_pairing)
        if Service.AIRPLAY in device.services:
            # On a device with full AirPlay, pyatv also lists AirPlay audio (RAOP) as needing
            # pairing, but the Apple TV never shows a PIN for it. Pair AirPlay only.
            wanted.discard(Service.RAOP)
    services = [s for s in _PAIRING_ORDER if s in wanted]
    if not services:
        printer.line(f"{printer.label(device)} needs no pairing.")
        return 0
    if args.pin_file is not None:
        args.pin_file.unlink(missing_ok=True)  # never reuse a PIN from an earlier run

    def on_pairing(event: PairingStateChanged) -> None:
        if event.state is PairingState.PIN_REQUIRED and args.pin_file is not None:
            where = printer.text(str(args.pin_file))
            printer.line(f"  The device is showing a PIN. Waiting for it in {where}")
        elif event.state is PairingState.FAILED:
            printer.line(f"  Pairing failed ({event.reason})")
        elif event.state is PairingState.PAIRED:
            printer.line("  Paired")

    engine.bus.subscribe(PairingStateChanged, on_pairing)
    failures = 0
    for service in services:
        if not args.service and service not in engine.device(device.id).needs_pairing:
            continue  # covered by an earlier pairing in this run
        printer.line(f"Pairing {service.value} with {printer.label(device)}")
        try:
            await engine.pair(device.id, service, _pin_provider(args), pin_timeout=args.pin_timeout)
        except PairingError:
            failures += 1
    return 1 if failures else 0


async def _connect(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    targets = _select(await engine.scan(), args, printer, single=False)
    if not targets:
        return 1
    names = {d.id: printer.label(d) for d in targets}

    def on_state(event: ConnectionStateChanged) -> None:
        label = names.get(event.device_id, "?")
        if event.state is ConnectionState.WAITING:
            detail = f"retrying in {event.retry_in:.1f} s ({event.reason})"
        elif event.state is ConnectionState.FAILED:
            detail = f"gave up ({event.reason})"
        else:
            detail = event.state.value
        printer.line(f"  {label}: {detail}")

    engine.bus.subscribe(ConnectionStateChanged, on_state)
    ok = 0
    for device in targets:
        try:
            await engine.connect(
                device.id,
                timeout=args.connect_timeout,
                max_attempts=None if args.keep else 3,
            )
        except (ConnectionFailedError, TimeoutError):
            await engine.disconnect(device.id)
            continue
        ok += 1
        if not args.keep:
            await asyncio.sleep(args.hold)
            await engine.disconnect(device.id)
    if args.keep:
        printer.line("Staying connected. Press Ctrl+C to disconnect.")
        await asyncio.Event().wait()
    verb = "Connected to" if args.keep else "Connected to and disconnected from"
    printer.line(f"{verb} {ok} of {len(targets)} device(s)")
    return 0 if ok == len(targets) else 1


async def _forget(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    selected = _select(await engine.scan(), args, printer, single=True)
    if not selected:
        return 1
    device = selected[0]
    removed = await engine.forget(device.id)
    printer.line(
        f"Forgot {printer.label(device)}" if removed else "No stored credentials for that device"
    )
    return 0


async def _diagnose(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    await engine.scan()  # registers current device names, so old logs get them redacted too
    settings = SettingsStore(paths.settings_file()).load().to_json()
    out_dir: Path = args.out or paths.data_dir() / "diagnostics"
    bundle = engine.diagnostics(out_dir, log_dir=paths.log_dir(), settings=settings)
    printer.line(f"Wrote {printer.text(str(bundle))}")
    printer.line("Check its contents before sharing it.")
    return 0


def _now_playing_line(now: NowPlaying, printer: _Printer, show_private: bool) -> str:
    """One line about what's playing. Titles are hidden unless --show-private."""

    def hidden(value: str | None) -> str | None:
        return value if show_private or value is None else "(hidden)"

    parts = [now.state.value, now.media_type.value]
    if now.app_name:
        parts.append(f"app: {now.app_name}")
    title = hidden(now.title)
    if title:
        parts.append(f"title: {title}")
    if now.position is not None and now.total_time:
        parts.append(f"{now.position:.0f}/{now.total_time:.0f} s")
    return printer.text("  ".join(parts))


async def _with_controls(
    engine: Engine,
    args: argparse.Namespace,
    printer: _Printer,
    action: Callable[[DeviceControls, ControlStatus], Awaitable[int]],
) -> int:
    """Connect to one device, run `action` on its controls, then disconnect."""
    selected = _select(await engine.scan(), args, printer, single=True)
    if not selected:
        return 1
    device = selected[0]
    ready = asyncio.ensure_future(
        engine.bus.wait_for(ControlsAvailable, lambda e: e.device_id == device.id, timeout=30)
    )
    try:
        await engine.connect(device.id, timeout=30, max_attempts=3)
        status = (await ready).status
    except (ConnectionFailedError, TimeoutError):
        ready.cancel()
        printer.line(f"Could not connect to {printer.label(device)}")
        await engine.disconnect(device.id)
        return 1
    try:
        return await action(engine.controls(device.id), status)
    except ControlError as exc:
        printer.line(f"{printer.label(device)}: {exc}")
        return 1
    except ValueError as exc:
        printer.line(str(exc))
        return 1
    finally:
        await engine.disconnect(device.id)


async def _controls(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    async def show(_controls: DeviceControls, status: ControlStatus) -> int:
        printer.line("Can: " + (", ".join(sorted(c.value for c in status.capabilities)) or "-"))
        level = "" if status.volume is None else f" (now {status.volume:.0f})"
        printer.line(f"Volume: {status.volume_control.value}{level}")
        printer.line(f"Power: {status.power.value}")
        printer.line(
            "Playing: " + _now_playing_line(status.now_playing, printer, args.show_private)
        )
        return 0

    return await _with_controls(engine, args, printer, show)


async def _remote(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    async def press(controls: DeviceControls, _status: ControlStatus) -> int:
        for index, key in enumerate(args.keys):
            if index:
                await asyncio.sleep(args.gap)
            started = time.perf_counter()
            await controls.press(RemoteKey(key), KeyAction(args.action))
            printer.line(f"  {key}: sent in {(time.perf_counter() - started) * 1000:.0f} ms")
        return 0

    return await _with_controls(engine, args, printer, press)


async def _media(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    async def send(controls: DeviceControls, _status: ControlStatus) -> int:
        await controls.media(MediaCommand(args.media_command))
        printer.line(f"  {args.media_command}: sent")
        return 0

    return await _with_controls(engine, args, printer, send)


async def _playing(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    async def show(controls: DeviceControls, status: ControlStatus) -> int:
        printer.line(_now_playing_line(status.now_playing, printer, args.show_private))
        if args.watch > 0:

            def on_change(event: NowPlayingChanged) -> None:
                if event.device_id == controls.device_id:
                    printer.line(_now_playing_line(event.now_playing, printer, args.show_private))

            unsubscribe = engine.bus.subscribe(NowPlayingChanged, on_change)
            try:
                await asyncio.sleep(args.watch)
            finally:
                unsubscribe()
        return 0

    return await _with_controls(engine, args, printer, show)


async def _power(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    async def run(controls: DeviceControls, status: ControlStatus) -> int:
        if args.state is None:
            printer.line(f"Power: {status.power.value}")
            return 0
        await controls.set_power(args.state == "on")
        printer.line(f"  power {args.state}: sent")
        return 0

    return await _with_controls(engine, args, printer, run)


VOLUME_HINT = (
    "  This device takes no volume changes. An Apple TV set to change volume by infrared (IR)"
    " leaves it to its own remote. If the TV supports HDMI-CEC, Settings > Remotes and"
    " Devices > Volume Control may offer a CEC option; otherwise use the TV remote."
)


async def _volume(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    async def run(controls: DeviceControls, status: ControlStatus) -> int:
        change: str | None = args.change
        if change is None:
            level = "" if status.volume is None else f", level {status.volume:.0f}"
            printer.line(f"Volume control: {status.volume_control.value}{level}")
            if status.volume_control is VolumeControl.NONE:
                printer.line(VOLUME_HINT)
            return 0
        if change in ("up", "down"):
            await (controls.volume_up() if change == "up" else controls.volume_down())
        else:
            await controls.set_volume(float(change))
        printer.line(f"  volume {change}: sent")
        return 0

    return await _with_controls(engine, args, printer, run)


async def _apps(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    async def run(controls: DeviceControls, _status: ControlStatus) -> int:
        for app in sorted(await controls.apps(), key=lambda a: a.name.casefold()):
            printer.line(f"  {app.name}  ({app.id})")
        return 0

    return await _with_controls(engine, args, printer, run)


async def _launch(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    async def run(controls: DeviceControls, _status: ControlStatus) -> int:
        await controls.launch(args.app_id)
        printer.line(f"  launch {args.app_id}: sent")
        return 0

    return await _with_controls(engine, args, printer, run)


async def _type(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    async def run(controls: DeviceControls, _status: ControlStatus) -> int:
        await controls.set_text(args.text)
        printer.line("  text: sent")
        return 0

    return await _with_controls(engine, args, printer, run)


async def _stream(engine: Engine, args: argparse.Namespace, printer: _Printer) -> int:
    selected = _select(await engine.scan(), args, printer, single=True)
    if not selected:
        return 1
    device = selected[0]
    label = printer.label(device)
    failed = asyncio.Event()

    def on_stream(event: AudioStreamChanged) -> None:
        if event.device_id != device.id:
            return
        reason = f" ({event.reason})" if event.reason else ""
        printer.line(f"  {label}: {event.state.value}{reason}")
        if event.state is StreamState.FAILED:
            failed.set()

    engine.bus.subscribe(AudioStreamChanged, on_stream)
    try:
        await engine.connect(device.id, timeout=30, max_attempts=3)
        await engine.start_audio(device.id, volume=args.volume)
    except (ConnectionFailedError, TimeoutError):
        printer.line(f"Could not connect to {label}")
        return 1
    except ValueError as exc:
        printer.line(str(exc))
        return 1
    printer.line("Streaming. Press Ctrl+C to stop." if not args.seconds else "Streaming.")
    started = time.perf_counter()
    try:
        while not failed.is_set():
            elapsed = time.perf_counter() - started
            if args.seconds and elapsed >= args.seconds:
                break
            wait = args.stats_every
            if args.seconds:
                wait = min(wait, args.seconds - elapsed)
            with suppress(TimeoutError):
                await asyncio.wait_for(failed.wait(), max(wait, 0.01))
            stats = engine.audio_stats(device.id)
            if stats is not None:
                printer.line(
                    f"  sent {stats.sent_seconds:.1f} s, dropped {stats.dropped_seconds:.2f} s,"
                    f" filled {stats.silence_seconds:.2f} s, buffered {stats.buffered_ms:.0f} ms,"
                    f" underruns {stats.underruns}"
                )
    finally:
        await engine.stop_audio(device.id)
    return 1 if failed.is_set() else 0


_COMMANDS = {
    "stream": _stream,
    "controls": _controls,
    "remote": _remote,
    "media": _media,
    "playing": _playing,
    "power": _power,
    "volume": _volume,
    "apps": _apps,
    "launch": _launch,
    "type": _type,
    "diagnose": _diagnose,
    "discover": _discover,
    "watch": _watch,
    "pair": _pair,
    "connect": _connect,
    "forget": _forget,
}


async def _run(
    backend: Backend, args: argparse.Namespace, printer: _Printer, redactor: Redactor
) -> int:
    engine = Engine(
        backend,
        redactor=redactor,
        scan_timeout=args.timeout,
        discovery_interval=getattr(args, "interval", 10.0),
    )
    await engine.open()
    try:
        return await _COMMANDS[args.command](engine, args, printer)
    finally:
        await engine.close()


def main(
    argv: Sequence[str] | None = None,
    *,
    backend_factory: BackendFactory = _default_backend,
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
    try:
        return asyncio.run(_run(backend_factory(), args, printer, redactor))
    except KeyboardInterrupt:
        return 130
