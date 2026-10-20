"""Spike A: pair with the Apple TV, send remote commands, read now-playing.

Throwaway spike code (Phase 0). It answers one question: does pyatv pair with and control
the reference Apple TV from Windows? Findings go into docs/ROADMAP.md.

Privacy: the device is picked by model, and nothing that identifies it (name, address,
identifier) is printed. Pairing keys are kept by pyatv's file storage in the git-ignored
local/ folder.

PIN entry: `pair` waits for the PIN in local/spike-a/pin.txt, so it can run unattended
while the tester reads the PIN off the TV.

Usage (from the repo root, with the dev virtualenv's python.exe):
    python spikes/spike_a_appletv.py find
    python spikes/spike_a_appletv.py pair companion
    python spikes/spike_a_appletv.py pair airplay
    python spikes/spike_a_appletv.py info
    python spikes/spike_a_appletv.py remote home down select menu
    python spikes/spike_a_appletv.py power off|on|state
    python spikes/spike_a_appletv.py playing [seconds]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import pyatv
from pyatv.const import DeviceModel, FeatureState, Protocol
from pyatv.interface import AppleTV, BaseConfig
from pyatv.storage.file_storage import FileStorage

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "local" / "spike-a"
STORAGE_FILE = STATE_DIR / "pyatv-storage.json"
PIN_FILE = STATE_DIR / "pin.txt"

TARGET_MODEL = DeviceModel.AppleTV4KGen2
PROTOCOLS = {"companion": Protocol.Companion, "airplay": Protocol.AirPlay}
REMOTE_KEYS = {
    "up", "down", "left", "right", "select", "menu", "home", "play_pause",
    "play", "pause", "volume_up", "volume_down", "top_menu", "control_center",
}


async def open_storage() -> FileStorage:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    storage = FileStorage(str(STORAGE_FILE), asyncio.get_running_loop())
    await storage.load()
    return storage


async def find_target(storage: FileStorage) -> BaseConfig:
    started = time.perf_counter()
    configs = await pyatv.scan(asyncio.get_running_loop(), timeout=5, storage=storage)
    elapsed = time.perf_counter() - started
    matches = [c for c in configs if c.device_info.model == TARGET_MODEL]
    print(f"scan: {len(configs)} device(s) in {elapsed:.1f} s, {len(matches)} matching model")
    if len(matches) != 1:
        sys.exit("expected exactly one Apple TV 4K (2nd gen); stopping")
    conf = matches[0]
    info = conf.device_info
    print(f"target: {info.model.name}, {info.operating_system.name} {info.version}")
    for service in conf.services:
        paired = "has credentials" if service.credentials else "not paired"
        print(f"  {service.protocol.name}: pairing={service.pairing.name}, {paired}")
    return conf


async def wait_for_pin(timeout: float = 180.0) -> int:
    PIN_FILE.unlink(missing_ok=True)
    print(f"waiting up to {int(timeout)} s for the PIN in local/spike-a/pin.txt", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if PIN_FILE.exists():
            text = PIN_FILE.read_text(encoding="utf-8").strip()
            PIN_FILE.unlink(missing_ok=True)
            if text.isdigit():
                return int(text)
            print("PIN file did not hold digits; still waiting", flush=True)
        await asyncio.sleep(0.5)
    sys.exit("no PIN received; pairing abandoned")


async def cmd_pair(protocol_name: str) -> None:
    storage = await open_storage()
    conf = await find_target(storage)
    protocol = PROTOCOLS[protocol_name]
    handler = await pyatv.pair(conf, protocol, asyncio.get_running_loop(), storage=storage)
    try:
        await handler.begin()
        if handler.device_provides_pin:
            print(f"{protocol.name}: a PIN should now be showing on the TV", flush=True)
            handler.pin(await wait_for_pin())
        else:
            print(f"{protocol.name}: device expects us to provide a PIN (unexpected)")
        await handler.finish()
        if handler.has_paired:
            await storage.save()
            print(f"{protocol.name}: paired, credentials saved in local/")
        else:
            print(f"{protocol.name}: pairing did not complete")
    finally:
        await handler.close()


async def connect(storage: FileStorage) -> AppleTV:
    conf = await find_target(storage)
    started = time.perf_counter()
    atv = await pyatv.connect(conf, asyncio.get_running_loop(), storage=storage)
    print(f"connected in {time.perf_counter() - started:.1f} s")
    return atv


async def close(atv: AppleTV) -> None:
    await asyncio.gather(*atv.close())


async def cmd_info() -> None:
    atv = await connect(await open_storage())
    try:
        available = [
            name.name
            for name, info in atv.features.all_features().items()
            if info.state == FeatureState.Available
        ]
        print(f"available features ({len(available)}): {', '.join(sorted(available))}")
    finally:
        await close(atv)


async def cmd_remote(keys: list[str]) -> None:
    bad = [k for k in keys if k not in REMOTE_KEYS]
    if bad:
        sys.exit(f"unknown key(s): {', '.join(bad)}; choose from {', '.join(sorted(REMOTE_KEYS))}")
    atv = await connect(await open_storage())
    try:
        for key in keys:
            started = time.perf_counter()
            await getattr(atv.remote_control, key)()
            print(f"sent {key} ({(time.perf_counter() - started) * 1000:.0f} ms)", flush=True)
            await asyncio.sleep(1.5)
    finally:
        await close(atv)


async def cmd_power(action: str) -> None:
    atv = await connect(await open_storage())
    try:
        if action == "off":
            await atv.power.turn_off()
        elif action == "on":
            await atv.power.turn_on()
        await asyncio.sleep(2)
        print(f"power state: {atv.power.power_state.name}")
    finally:
        await close(atv)


async def cmd_playing(seconds: int) -> None:
    atv = await connect(await open_storage())
    try:
        deadline = time.monotonic() + seconds
        last = ""
        while True:
            playing = await atv.metadata.playing()
            app = atv.metadata.app
            line = (
                f"app={app.name if app else '-'} state={playing.device_state.name} "
                f"type={playing.media_type.name} title={playing.title!r} "
                f"artist={playing.artist!r} position={playing.position}/{playing.total_time}"
            )
            if line != last:
                print(line, flush=True)
                last = line
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(2)
    finally:
        await close(atv)


async def cmd_find() -> None:
    await find_target(await open_storage())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("find")
    pair = sub.add_parser("pair")
    pair.add_argument("protocol", choices=sorted(PROTOCOLS))
    sub.add_parser("info")
    remote = sub.add_parser("remote")
    remote.add_argument("keys", nargs="+")
    power = sub.add_parser("power")
    power.add_argument("action", choices=["off", "on", "state"])
    playing = sub.add_parser("playing")
    playing.add_argument("seconds", nargs="?", type=int, default=0)
    args = parser.parse_args()

    if args.command == "find":
        coro = cmd_find()
    elif args.command == "pair":
        coro = cmd_pair(args.protocol)
    elif args.command == "info":
        coro = cmd_info()
    elif args.command == "remote":
        coro = cmd_remote(args.keys)
    elif args.command == "power":
        coro = cmd_power(args.action)
    else:
        coro = cmd_playing(args.seconds)
    asyncio.run(coro)


if __name__ == "__main__":
    main()
