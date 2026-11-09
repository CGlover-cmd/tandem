"""Hardware check for the music library (Phase 6): Tandem's own player to real speakers.

Throwaway check code. It drives the real engine (pyatv, the player, the audio hub) without
the window:
    find    list the speakers that take audio, by kind and model only
    file    play a generated 30 s test file (clicks every half second over a chord) to the
            chosen speakers, so the listener can hear whether they play together
    radio   play the first MP3/Ogg station Radio Browser finds for a generic word, for an
            hour, and write counts only (underruns, reconnects, errors, seconds sent) to local/

Privacy: speakers are picked by model, never by name; no name, address, id, station name or
URL is printed or written. State (pairing, logs) stays in TANDEM_HOME, which must be under
local/. Usage, from the repo root with the clone's venv:
    python spikes/music_speakers.py find
    python spikes/music_speakers.py file --model "<model>" --model "<model>"
    python spikes/music_speakers.py radio --model ... --minutes 60 --word jazz
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import struct
import sys
import time
import wave
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "local" / "music-hw"
RATE = 44100


def _require_local_home() -> None:
    home = os.environ.get("TANDEM_HOME", "")
    if not home or not Path(home).resolve().is_relative_to((ROOT / "local").resolve()):
        sys.exit("Set TANDEM_HOME to a folder under local/ first.")


def make_test_file(seconds: float = 30.0) -> Path:
    """A soft A-major chord with a short click every half second (easy to hear sync)."""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "sync-test.wav"
    frames = int(RATE * seconds)
    data = bytearray()
    click_len = int(RATE * 0.012)
    for n in range(frames):
        t = n / RATE
        fade = min(1.0, t / 0.5, (seconds - t) / 0.5)
        chord = sum(math.sin(2 * math.pi * f * t) for f in (220.0, 277.18, 329.63)) / 3
        sample = 0.18 * fade * chord
        pos = n % (RATE // 2)
        if pos < click_len:
            sample += 0.6 * (1 - pos / click_len) * math.sin(2 * math.pi * 1760 * t)
        value = int(max(-1.0, min(1.0, sample)) * 32767)
        data += struct.pack("<hh", value, value)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(bytes(data))
    return path


async def open_engine():  # type: ignore[no-untyped-def]
    from tandem.engine import paths
    from tandem.engine.adapters.credential_vault import CredentialVault
    from tandem.engine.adapters.pyatv_adapter import PyatvBackend
    from tandem.engine.events import EventBus
    from tandem.engine.logs import configure_logging
    from tandem.engine.redact import Redactor
    from tandem.engine.service import Engine

    redactor = Redactor()
    configure_logging(redactor, log_dir=paths.log_dir())
    engine = Engine(
        PyatvBackend(CredentialVault(paths.credentials_file())), bus=EventBus(), redactor=redactor
    )
    await engine.open()
    await engine.scan()
    return engine


def speakers(engine):  # type: ignore[no-untyped-def]
    from tandem.engine.models import DeviceKind

    found = [
        d
        for d in engine.registry.devices()
        if d.kind in (DeviceKind.HOMEPOD, DeviceKind.RECEIVER) and engine_can_stream(d)
    ]
    return sorted(found, key=lambda d: (d.model, d.id))


def engine_can_stream(device) -> bool:  # type: ignore[no-untyped-def]
    return any(s.name in ("RAOP", "AIRPLAY") for s in device.services)


def pick(engine, models: list[str]):  # type: ignore[no-untyped-def]
    chosen = []
    available = speakers(engine)
    for model in models:
        match = next((d for d in available if d.model == model and d not in chosen), None)
        if match is None:
            sys.exit(f"No speaker of model {model!r} found.")
        chosen.append(match)
    return chosen


async def cmd_find() -> None:
    engine = await open_engine()
    try:
        counts = Counter((d.kind.value, d.model) for d in speakers(engine))
        for (kind, model), n in sorted(counts.items()):
            print(f"{kind:9} {model!r} x{n}")
    finally:
        await engine.close()


async def start_outputs(engine, devices) -> list[str]:  # type: ignore[no-untyped-def]
    from tandem.engine.service import AudioSource

    await engine.set_audio_source(AudioSource.PLAYER)
    labels = []
    for n, device in enumerate(devices):
        await engine.start_output(device.id, volume=None)
        labels.append(f"speaker{n + 1} ({device.model})")
    return labels


async def cmd_file(models: list[str], seconds: float) -> None:
    from tandem.engine.player import NewTrack, TrackKind

    path = make_test_file(seconds)
    engine = await open_engine()
    try:
        devices = pick(engine, models)
        labels = await start_outputs(engine, devices)
        print("Outputs:", ", ".join(labels), flush=True)
        await asyncio.sleep(2)
        engine.player.play_tracks([NewTrack(TrackKind.FILE, str(path), "Sync test")])
        await asyncio.sleep(seconds + 4)
        for n, device in enumerate(devices):
            stats = engine.audio_stats(device.id)
            if stats is not None:
                print(
                    f"speaker{n + 1}: sent {stats.sent_seconds:.1f} s, underruns {stats.underruns},"
                    f" silence {stats.silence_seconds:.1f} s, dropped {stats.dropped_seconds:.1f} s"
                )
        print("player error:", engine.player.status.error)
    finally:
        for device in devices if "devices" in locals() else []:
            await engine.stop_output(device.id)
        await engine.close()


async def cmd_radio(models: list[str], minutes: float, word: str) -> None:
    from tandem.engine.adapters.radio_browser import search_stations
    from tandem.engine.audio import AudioStreamChanged, StreamState
    from tandem.engine.player import NewTrack, PlayerChanged, PlayerState, TrackKind
    from tandem.engine.radio import Radio

    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / "radio-run.json"
    engine = await open_engine()
    devices = []
    try:
        radio = Radio(engine.bus, search_stations, store=None)
        await radio.search(word)
        if not radio.status.results:
            sys.exit("No playable station found.")
        station = radio.status.results[0]
        devices = pick(engine, models)
        index = {d.id: f"speaker{n + 1}" for n, d in enumerate(devices)}
        counts: Counter[str] = Counter()
        states: dict[str, str] = {}

        def on_stream(event: AudioStreamChanged) -> None:
            label = index.get(event.device_id)
            if label is None:
                return
            before = states.get(label)
            states[label] = event.state.value
            counts[f"{label}.{event.state.value}"] += 1
            if event.state is StreamState.WAITING or (
                event.state is StreamState.STARTING and before == "streaming"
            ):
                counts[f"{label}.reconnects"] += 1
            if event.state is StreamState.FAILED:
                counts[f"{label}.errors"] += 1

        def on_player(event: PlayerChanged) -> None:
            if event.status.error is not None:
                counts[f"player.error.{event.status.error}"] += 1
            if event.status.state is PlayerState.STOPPED:
                counts["player.stopped"] += 1

        engine.bus.subscribe(AudioStreamChanged, on_stream)
        engine.bus.subscribe(PlayerChanged, on_player)
        labels = await start_outputs(engine, devices)
        await asyncio.sleep(2)
        engine.player.play_tracks([NewTrack(TrackKind.RADIO, station.url, "Radio")])
        started = time.monotonic()
        deadline = started + minutes * 60

        def write(final: bool) -> dict[str, object]:
            report: dict[str, object] = {
                "outputs": labels,
                "codec": station.codec,
                "bitrate": station.bitrate,
                "elapsed_min": round((time.monotonic() - started) / 60, 1),
                "final": final,
                "player_state": engine.player.status.state.value,
                "events": dict(counts),
            }
            for device in devices:
                stats = engine.audio_stats(device.id)
                if stats is not None:
                    report[index[device.id]] = {
                        "sent_s": round(stats.sent_seconds, 1),
                        "underruns": stats.underruns,
                        "silence_s": round(stats.silence_seconds, 1),
                        "dropped_s": round(stats.dropped_seconds, 1),
                    }
            report_path.write_text(json.dumps(report, indent=2), "utf-8")
            return report

        while time.monotonic() < deadline:
            await asyncio.sleep(30)
            if engine.player.status.state is PlayerState.STOPPED:
                counts["player.restarts"] += 1
                engine.player.play_tracks([NewTrack(TrackKind.RADIO, station.url, "Radio")])
            write(False)
        print(json.dumps(write(True), indent=2))
    finally:
        engine.player.stop()
        for device in devices:
            await engine.stop_output(device.id)
        await engine.close()


def main() -> None:
    _require_local_home()
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("find")
    file = sub.add_parser("file")
    file.add_argument("--model", action="append", required=True)
    file.add_argument("--seconds", type=float, default=30.0)
    radio = sub.add_parser("radio")
    radio.add_argument("--model", action="append", required=True)
    radio.add_argument("--minutes", type=float, default=60.0)
    radio.add_argument("--word", default="jazz")
    args = parser.parse_args()
    if args.command == "find":
        asyncio.run(cmd_find())
    elif args.command == "file":
        asyncio.run(cmd_file(args.model, args.seconds))
    else:
        asyncio.run(cmd_radio(args.model, args.minutes, args.word))
    sys.stdout.flush()
    os._exit(0)  # pyatv/aiohttp leftovers can keep the process alive


if __name__ == "__main__":
    main()
