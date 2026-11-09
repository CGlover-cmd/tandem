"""Spike H: do AirPlay 2 speakers follow Tandem's PTP clock and play together? (ADR-0020)

Throwaway check code. It plays a click track whose content is set by the PTP clock: at every
whole second of that clock, a short beep, its note cycling through four (C, E, G, high C).
Speakers that follow the clock beep together on the same note. Speakers that pick their own
delay beep apart, or on different notes when they are whole seconds out.

    find      list the speakers that take audio, by kind and model, and whether they
              advertise PTP
    compare   PTP timing for --seconds, a pause, then pyatv's usual NTP timing for --seconds,
              to the chosen speakers at once; writes counts to local/ptp-hw/compare.json

Privacy: speakers are picked by model, never by name; no name, address or id is printed.
Counts only. pyatv's debug log (which does hold addresses) goes to local/ptp-hw/ only.
State stays in TANDEM_HOME, which must be under local/. Run under the installed app's
Python (the firewall lets that program reach the speakers):
    "C:\\Program Files\\Tandem\\python\\pythonw.exe" spikes/run_under_app.py spikes/spike_h_ptp.py find
    ... spikes/spike_h_ptp.py compare --model "<model>" --model "<model>" --seconds 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import struct
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "local" / "ptp-hw"
RATE = 44100
NOTES = (523.25, 659.25, 783.99, 1046.5)  # C5 E5 G5 C6
BEEP_S = 0.08


def _require_local_home() -> None:
    home = os.environ.get("TANDEM_HOME", "")
    if not home or not Path(home).resolve().is_relative_to((ROOT / "local").resolve()):
        sys.exit("Set TANDEM_HOME to a folder under local/ first.")


def beep_sample(t_ns: int) -> int:
    """The click track at PTP time t_ns: a decaying beep at each whole second."""
    second, into = divmod(t_ns, 1_000_000_000)
    t = into / 1e9
    if t >= BEEP_S:
        return 0
    freq = NOTES[second % len(NOTES)]
    env = (1 - t / BEEP_S) ** 2
    return int(0.5 * env * math.sin(2 * math.pi * freq * t) * 32767)


class ClickSource:
    """A pyatv AudioSource whose content follows a clock.

    With a PtpTimeline, frame k plays at timeline.play_ns(k), and carries the click track at
    that time. Without one (NTP run), frame k is given the content for "first read + lead +
    k/rate": what an in-sync speaker would play if it honoured the sender's timing."""

    def __init__(self, timeline: Any | None, seconds: float, lead_ns: int) -> None:
        self._timeline = timeline
        self._frames_left = int(seconds * RATE)
        self._lead_ns = lead_ns
        self._k = 0
        self._t0: int | None = None

    def _play_ns(self, k: int) -> int:
        if self._timeline is not None and self._timeline.anchored:
            return self._timeline.play_ns(k)
        from tandem.engine.adapters import ptp

        if self._t0 is None:
            self._t0 = ptp.now_ns() + self._lead_ns
        return self._t0 + k * 1_000_000_000 // RATE

    async def readframes(self, nframes: int) -> bytes:
        if self._frames_left <= 0:
            return b""
        n = min(nframes, self._frames_left)
        out = bytearray()
        for i in range(n):
            value = beep_sample(self._play_ns(self._k + i))
            out += struct.pack(">hh", value, value)  # pyatv sends big-endian samples
        self._k += n
        self._frames_left -= n
        return bytes(out)

    async def get_metadata(self) -> Any:
        from pyatv.interface import MediaMetadata

        return MediaMetadata(title="Tandem timing test", artist="Tandem")

    async def close(self) -> None:
        pass

    @property
    def sample_rate(self) -> int:
        return RATE

    @property
    def channels(self) -> int:
        return 2

    @property
    def sample_size(self) -> int:
        return 2

    @property
    def duration(self) -> int:
        return 0


def _install_source_hook() -> None:
    import pyatv.protocols.raop as raop

    original = raop.open_source

    async def open_source(source: Any, *args: Any) -> Any:
        if isinstance(source, ClickSource):
            return source
        return await original(source, *args)

    raop.open_source = open_source  # type: ignore[assignment]


async def open_backend() -> Any:
    from tandem.engine import paths
    from tandem.engine.adapters.credential_vault import CredentialVault
    from tandem.engine.adapters.pyatv_adapter import PyatvBackend

    backend = PyatvBackend(CredentialVault(paths.credentials_file()))
    await backend.load()
    return backend


def _speakers(devices: Any) -> list[Any]:
    from tandem.engine.models import DeviceKind, Service

    found = [
        d
        for d in devices
        if d.kind in (DeviceKind.HOMEPOD, DeviceKind.RECEIVER) and Service.RAOP in d.services
    ]
    return sorted(found, key=lambda d: (d.model, d.id))


def _raop_properties(backend: Any, device_id: str) -> dict[str, str]:
    from pyatv.const import Protocol

    config = backend._configs[device_id]  # spike: reach in for the TXT record
    service = config.get_service(Protocol.RAOP)
    return dict(service.properties) if service else {}


async def cmd_find() -> None:
    from tandem.engine.adapters import pyatv_ptp

    backend = await open_backend()
    devices = _speakers(await backend.scan(5))
    counts = Counter(
        (d.kind.value, d.model, pyatv_ptp.supports_ptp(_raop_properties(backend, d.id)))
        for d in devices
    )
    for (kind, model, has_ptp), n in sorted(counts.items()):
        print(f"{kind:9} {model!r} x{n}  PTP: {'yes' if has_ptp else 'no'}")


async def _play(atvs: list[Any], sources: list[ClickSource]) -> list[str | None]:
    async def one(atv: Any, source: ClickSource) -> str | None:
        try:
            await atv.stream.stream_file(source)
            return None
        except Exception as exc:  # report the kind only: messages can carry addresses
            cause = exc.__cause__
            return type(exc).__name__ + (f" <- {type(cause).__name__}" if cause else "")

    return list(await asyncio.gather(*(one(a, s) for a, s in zip(atvs, sources, strict=True))))


async def cmd_compare(models: list[str], seconds: float, lead: float, pause: float) -> None:
    from tandem.engine.adapters import ptp, pyatv_ptp

    OUT.mkdir(parents=True, exist_ok=True)
    pyatv_log = logging.FileHandler(OUT / "pyatv-debug.log", mode="w", encoding="utf-8")
    pyatv_log.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    logging.getLogger("pyatv").addHandler(pyatv_log)
    logging.getLogger("pyatv").setLevel(logging.DEBUG)
    _install_source_hook()

    backend = await open_backend()
    devices = _speakers(await backend.scan(5))
    chosen = []
    for model in models:
        match = next((d for d in devices if d.model == model and d not in chosen), None)
        if match is None:
            sys.exit(f"No speaker of model {model!r} found.")
        chosen.append(match)
    labels = [f"speaker{n + 1} ({d.model})" for n, d in enumerate(chosen)]
    report: dict[str, Any] = {"outputs": labels, "lead_s": lead, "seconds": seconds}

    links = []
    for device in chosen:
        links.append(await backend.connector(device.id)(lambda _exc: None))
    atvs = [link.atv for link in links]
    addresses = [str(backend._configs[d.id].address) for d in chosen]  # never printed

    master = ptp.PtpMaster()
    try:
        await master.start()
    except ptp.PtpError as exc:
        report["ptp_start_error"] = str(exc)
        print(json.dumps(report, indent=2))
        return

    group = str(uuid.uuid4()).upper()
    lead_ns = int(lead * 1e9)
    streams = []
    for device, address in zip(chosen, addresses, strict=True):
        has_ptp = pyatv_ptp.supports_ptp(_raop_properties(backend, device.id))
        stream = pyatv_ptp.PtpStream(master, group, lead_ns) if has_ptp else None
        if stream is not None:
            pyatv_ptp.register(address, stream)
        streams.append(stream)

    print("PTP run: listen for one beep per second, same note on every speaker.", flush=True)
    started = time.monotonic()
    sources = [ClickSource(s.timeline if s else None, seconds, lead_ns) for s in streams]
    errors = await _play(atvs, sources)
    ptp_run: dict[str, Any] = {"elapsed_s": round(time.monotonic() - started, 1)}
    for label, stream, address, error in zip(labels, streams, addresses, errors, strict=True):
        entry: dict[str, Any] = {"ptp": stream is not None, "error": error}
        if stream is not None:
            stats = master.stats(stream.peer_address) if stream.peer_address else None
            entry.update(
                {
                    "peer_is_rtsp_address": stream.peer_address == address,
                    "setpeers_status": stream.setpeers_status,
                    "sync_packets": stream.sync_packets,
                }
            )
            if stats is not None:
                entry.update(
                    {
                        "delay_requests": stats.delay_requests,
                        "pdelay_requests": stats.pdelay_requests,
                        "announces_from_speaker": stats.announces,
                        "speaker_priority1": stats.last_announce.priority1
                        if stats.last_announce
                        else None,
                        "other_messages": stats.other,
                    }
                )
            pyatv_ptp.unregister(address)
        ptp_run[label] = entry
    report["ptp_run"] = ptp_run
    (OUT / "compare.json").write_text(json.dumps(report, indent=2), "utf-8")
    await master.stop()

    await asyncio.sleep(pause)
    print("NTP run: pyatv's usual timing, for comparison.", flush=True)
    started = time.monotonic()
    sources = [ClickSource(None, seconds, lead_ns) for _ in chosen]
    errors = await _play(atvs, sources)
    report["ntp_run"] = {
        "elapsed_s": round(time.monotonic() - started, 1),
        **{label: {"error": error} for label, error in zip(labels, errors, strict=True)},
    }
    (OUT / "compare.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps(report, indent=2))
    for link in links:
        await link.close()


def main() -> None:
    _require_local_home()
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("find")
    compare = sub.add_parser("compare")
    compare.add_argument("--model", action="append", required=True)
    compare.add_argument("--seconds", type=float, default=30.0)
    compare.add_argument("--lead", type=float, default=2.0)
    compare.add_argument("--pause", type=float, default=5.0)
    args = parser.parse_args()
    if args.command == "find":
        asyncio.run(cmd_find())
    else:
        asyncio.run(cmd_compare(args.model, args.seconds, args.lead, args.pause))
    sys.stdout.flush()
    os._exit(0)  # pyatv/aiohttp leftovers can keep the process alive


if __name__ == "__main__":
    main()
