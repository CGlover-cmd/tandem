"""Spike B: play a test tone on the soundbar, then on each HomePod mini.

Throwaway spike code (Phase 0). It answers one question: can pyatv stream audio from Windows
to the reference speakers? The tester, in the room, confirms whether they hear each tone.
Findings go into docs/spikes/spike-b-audio.md.

Privacy: speakers are picked by kind, not by name. The soundbar is the one non-Apple device
that accepts audio streams (RAOP); the two HomePod minis are labelled homepod1 and homepod2 in
a fixed order. Nothing that identifies a device (name, address, identifier) is printed. The
tone file is written to the git-ignored local/ folder.

Usage (from the repo root, with the dev virtualenv's python.exe):
    python spikes/spike_b_audio.py find
    python spikes/spike_b_audio.py tone soundbar|homepod1|homepod2 [--seconds 5] [--volume 30]
"""

from __future__ import annotations

import argparse
import asyncio
import math
import struct
import sys
import time
import wave
from pathlib import Path

import pyatv
from pyatv.const import DeviceModel, Protocol
from pyatv.interface import BaseConfig, MediaMetadata

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "local" / "spike-b"

TARGETS = ("soundbar", "homepod1", "homepod2")
SAMPLE_RATE = 44100
FREQUENCY = 440.0


def make_tone(seconds: float) -> Path:
    """Write a stereo 16-bit 440 Hz sine tone with short fades, and return its path."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"tone-{seconds:g}s.wav"
    frames = int(SAMPLE_RATE * seconds)
    fade = int(SAMPLE_RATE * 0.05)
    data = bytearray()
    for n in range(frames):
        gain = min(1.0, n / fade, (frames - n) / fade)
        sample = int(0.5 * gain * 32767 * math.sin(2 * math.pi * FREQUENCY * n / SAMPLE_RATE))
        data += struct.pack("<hh", sample, sample)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(data))
    return path


def has_raop(conf: BaseConfig) -> bool:
    return conf.get_service(Protocol.RAOP) is not None


async def find_targets() -> dict[str, BaseConfig]:
    started = time.perf_counter()
    configs = await pyatv.scan(asyncio.get_running_loop(), timeout=5)
    elapsed = time.perf_counter() - started
    homepods = sorted(
        (c for c in configs if c.device_info.model == DeviceModel.HomePodMini),
        key=lambda c: c.identifier or "",
    )
    soundbars = [c for c in configs if c.device_info.model == DeviceModel.Unknown and has_raop(c)]
    print(f"scan: {len(configs)} device(s) in {elapsed:.1f} s")
    targets: dict[str, BaseConfig] = {}
    if len(soundbars) == 1:
        targets["soundbar"] = soundbars[0]
    else:
        print(f"expected one third-party speaker that takes audio streams, found {len(soundbars)}")
    for index, conf in enumerate(homepods[:2], start=1):
        targets[f"homepod{index}"] = conf
    if len(homepods) != 2:
        print(f"expected two HomePod minis, found {len(homepods)}")
    for label, conf in targets.items():
        info = conf.device_info
        version = f"{info.operating_system.name} {info.version}" if info.version else "os unknown"
        services = ", ".join(f"{s.protocol.name}:{s.pairing.name}" for s in conf.services)
        print(f"  {label}: {info.model.name}, {version}, {services}")
    return targets


async def cmd_find() -> None:
    await find_targets()


async def cmd_tone(target: str, seconds: float, volume: float) -> None:
    tone = make_tone(seconds)
    targets = await find_targets()
    if target not in targets:
        sys.exit(f"{target} not found; stopping")
    conf = targets[target]

    started = time.perf_counter()
    atv = await pyatv.connect(conf, asyncio.get_running_loop())
    print(f"connected in {time.perf_counter() - started:.1f} s", flush=True)
    try:
        await atv.audio.set_volume(volume)
        print(f"volume set to {volume:g}%", flush=True)
        print(f"streaming a {seconds:g} s {FREQUENCY:g} Hz tone to {target}", flush=True)
        started = time.perf_counter()
        await atv.stream.stream_file(
            str(tone), metadata=MediaMetadata(title="Tandem test tone", artist="Tandem")
        )
        total = time.perf_counter() - started
        print(f"stream finished in {total:.1f} s ({total - seconds:+.1f} s vs tone length)")
    finally:
        await asyncio.gather(*atv.close())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("find")
    tone = sub.add_parser("tone")
    tone.add_argument("target", choices=TARGETS)
    tone.add_argument("--seconds", type=float, default=5.0)
    tone.add_argument("--volume", type=float, default=30.0)
    args = parser.parse_args()

    if args.command == "find":
        asyncio.run(cmd_find())
    else:
        if not 0 <= args.volume <= 60:
            sys.exit("volume must be between 0 and 60 for this spike")
        asyncio.run(cmd_tone(args.target, args.seconds, args.volume))


if __name__ == "__main__":
    main()
