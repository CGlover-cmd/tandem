"""Spike F: the Raspberry Pi 3 as an AirPlay 2 audio test receiver (Phase 0).

Throwaway spike code. It answers one question: can shairport-sync on the test Pi stand in for a
real speaker, so later phases can test audio automatically, with no one listening? The Pi runs
shairport-sync (built for AirPlay 2, with nqptp) on demand, writing what it plays to a raw PCM
file instead of a sound card. The script streams a known test tone to it with pyatv, copies the
file back, and checks the audio sample by sample: length, pitch, gaps, glitches and level.

Receiver modes: 'classic' (AirPlay 1, the default) works with pyatv. 'airplay2' does not:
pyatv's AirPlay 2 sender asks for NTP timing, and shairport-sync's AirPlay 2 mode only does PTP.

The Pi is a test tool only. The shipped app never needs it.

Privacy: the Pi's host name comes from the TANDEM_PI_HOST environment variable and is never
printed. The receiver is picked by kind (the model shairport-sync advertises), never by name.
Nothing that identifies a device is printed. Captures and logs go to the git-ignored local/.

Usage (from the repo root, with the dev virtualenv's python.exe; TANDEM_PI_HOST set):
    python spikes/spike_f_pi_receiver.py receiver start|stop|status [--mode classic|airplay2]
    python spikes/spike_f_pi_receiver.py find
    python spikes/spike_f_pi_receiver.py tone [--seconds 5] [--volume 100] [--airplay auto|1|2]
                                              [--mode classic|airplay2]
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np
import pyatv
from pyatv.const import Protocol
from pyatv.interface import BaseConfig, MediaMetadata
from pyatv.settings import AirPlayVersion
from pyatv.storage.memory_storage import MemoryStorage

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "local" / "spike-f"
SSH_KEY = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".ssh" / "tandem_pi"
PI_USER = "tandem"
PI_DIR = "spike-f"  # under the Pi user's home
MODES = ("classic", "airplay2")
RECEIVER_NAME = "Tandem Test Receiver"  # invented, neutral; the script never selects by it

SAMPLE_RATE = 44100
FREQUENCY = 440.0
SOURCE_PEAK = 0.5  # the tone's peak, as a fraction of full scale
FADE_SECONDS = 0.05


# --- the Pi side -----------------------------------------------------------------------------


def pi_host() -> str:
    host = os.environ.get("TANDEM_PI_HOST")
    if not host:
        sys.exit("set TANDEM_PI_HOST to the test Pi's host name (it is never printed)")
    return host


def ssh(command: str, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    exe = shutil.which("ssh") or "ssh"
    return subprocess.run(
        [exe, "-i", str(SSH_KEY), "-o", "BatchMode=yes", f"{PI_USER}@{pi_host()}", command],
        capture_output=True, text=True, timeout=timeout,
    )


def scp_from_pi(remote: str, local: Path) -> None:
    exe = shutil.which("scp") or "scp"
    local.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [exe, "-q", "-i", str(SSH_KEY), "-o", "BatchMode=yes",
         f"{PI_USER}@{pi_host()}:{remote}", str(local)],
        check=True, timeout=120,
    )


def start_receiver(mode: str) -> str:
    """Shell script that starts shairport-sync, playing through its stdout back end into a file,
    pinned to 16-bit stereo at 44.1 kHz to match the source (an AirPlay 2 build otherwise writes
    32-bit at 48 kHz, even for classic sessions). mode 'airplay2' needs nqptp (PTP timing); 'classic' is
    AirPlay 1 (NTP timing) and doesn't."""
    nqptp = "sudo systemctl start nqptp" if mode == "airplay2" else "sudo systemctl stop nqptp"
    return f"""
set -e
mkdir -p ~/{PI_DIR}
if pgrep -x uxplay >/dev/null; then echo "UxPlay is running; stop it first"; exit 3; fi
pkill -x shairport-sync 2>/dev/null || true
sleep 1
{nqptp}
rm -f ~/{PI_DIR}/capture.raw ~/{PI_DIR}/receiver.log
echo 'stdout = {{ output_rate = 44100; output_format = "S16_LE"; output_channels = 2; }};' \
  > ~/{PI_DIR}/receiver.conf
nohup shairport-sync -c ~/{PI_DIR}/receiver.conf -a '{RECEIVER_NAME}' --service-type={mode} \
  -o stdout --statistics -v > ~/{PI_DIR}/capture.raw 2> ~/{PI_DIR}/receiver.log < /dev/null &
sleep 2
pgrep -x shairport-sync >/dev/null && echo "running ({mode})"
"""

STOP_RECEIVER = """
pkill -x shairport-sync 2>/dev/null || true
sudo systemctl stop nqptp
echo stopped
"""

STATUS_RECEIVER = """
echo "shairport-sync: $(pgrep -x shairport-sync >/dev/null && echo running || echo stopped)"
echo "nqptp: $(systemctl is-active nqptp)"
echo "version: $(shairport-sync -V 2>&1)"
"""


def cmd_receiver(action: str, mode: str = "classic") -> None:
    script = {"stop": STOP_RECEIVER, "status": STATUS_RECEIVER}.get(action) or start_receiver(mode)
    result = ssh(script)
    print(result.stdout.strip() or "(no output)")
    if result.returncode != 0:
        sys.exit(f"receiver {action} failed (exit {result.returncode}); see the Pi's log")


# --- finding the receiver --------------------------------------------------------------------


def is_shairport(conf: BaseConfig) -> bool:
    """shairport-sync advertises its own model string; pick by that, never by name."""
    for proto in (Protocol.RAOP, Protocol.AirPlay):
        service = conf.get_service(proto)
        if service is None:
            continue
        props = service.properties or {}
        if any("shairport" in str(props.get(key, "")).lower() for key in ("am", "model")):
            return True
    return False


async def find_receiver() -> BaseConfig | None:
    started = time.perf_counter()
    configs = await pyatv.scan(asyncio.get_running_loop(), timeout=5)
    found = [c for c in configs if is_shairport(c)]
    print(f"scan: {len(configs)} device(s) in {time.perf_counter() - started:.1f} s, "
          f"{len(found)} shairport-sync receiver(s)")
    if len(found) != 1:
        return None
    conf = found[0]
    services = ", ".join(f"{s.protocol.name}:{s.pairing.name}" for s in conf.services)
    print(f"  receiver: {services}")
    for proto in (Protocol.RAOP, Protocol.AirPlay):
        service = conf.get_service(proto)
        if service is not None:
            props = service.properties or {}
            model = props.get("am") or props.get("model") or "?"
            features = props.get("ft") or props.get("features") or "?"
            print(f"  {proto.name}: model {model}, features {features}")
    return conf


async def cmd_find() -> None:
    if await find_receiver() is None:
        sys.exit("expected exactly one shairport-sync receiver; is it started?")


# --- the tone and the check ------------------------------------------------------------------


def make_tone(seconds: float) -> Path:
    """Write a stereo 16-bit 440 Hz sine with short fades (same shape as Spike B)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"tone-{seconds:g}s.wav"
    frames = int(SAMPLE_RATE * seconds)
    fade = int(SAMPLE_RATE * FADE_SECONDS)
    data = bytearray()
    for n in range(frames):
        gain = min(1.0, n / fade, (frames - n) / fade)
        sample = int(SOURCE_PEAK * gain * 32767 * math.sin(2 * math.pi * FREQUENCY * n / SAMPLE_RATE))
        data += struct.pack("<hh", sample, sample)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(data))
    return path


def analyse(raw: bytes, seconds: float) -> dict[str, object]:
    """Check the received PCM against the tone that was sent."""
    pcm = np.frombuffer(raw[: len(raw) // 4 * 4], dtype="<i2").reshape(-1, 2).astype(np.float64)
    pcm /= 32768.0
    result: dict[str, object] = {"frames received": len(pcm)}
    if len(pcm) == 0:
        return result
    left, right = pcm[:, 0], pcm[:, 1]
    peak_all = float(np.max(np.abs(left)))
    if peak_all < 1e-3:
        result["verdict"] = "silence"
        return result

    # The tone is where the signal is above 5% of its own peak.
    loud = np.flatnonzero(np.abs(left) > 0.05 * peak_all)
    first, last = int(loud[0]), int(loud[-1])
    tone = left[first : last + 1]
    result["tone length (s)"] = round(len(tone) / SAMPLE_RATE, 3)
    result["expected length (s)"] = round(seconds - 2 * FADE_SECONDS * 0.05, 3)

    # Steady part: skip the fades plus a margin.
    margin = int(SAMPLE_RATE * (FADE_SECONDS + 0.05))
    steady = tone[margin:-margin] if len(tone) > 4 * margin else tone
    peak = float(np.max(np.abs(steady)))
    result["level vs source (dB)"] = round(20 * math.log10(peak / SOURCE_PEAK), 1)

    # Pitch from upward zero crossings.
    ups = np.flatnonzero((steady[:-1] < 0) & (steady[1:] >= 0))
    if len(ups) > 2:
        result["pitch (Hz)"] = round(float((len(ups) - 1) * SAMPLE_RATE / (ups[-1] - ups[0])), 2)

    # Gaps: a 440 Hz sine stays near zero for well under a sample; >1 ms near zero is a dropout.
    quiet = np.abs(steady) < 0.02 * peak
    runs, run = [], 0
    for q in quiet:
        if q:
            run += 1
        elif run:
            runs.append(run)
            run = 0
    gap_len = int(SAMPLE_RATE * 0.001)
    gaps = [r for r in runs if r >= gap_len]
    result["gaps > 1 ms"] = len(gaps)

    # Glitches: a jump between samples bigger than a clean sine of this level can make.
    max_step = peak * 2 * math.pi * FREQUENCY / SAMPLE_RATE
    steps = np.abs(np.diff(steady))
    result["glitches"] = int(np.count_nonzero(steps > 1.5 * max_step))

    # Distortion: residual after removing the best-fit 440 Hz sine, relative to the tone.
    n = np.arange(len(steady))
    basis = np.column_stack([np.sin(2 * np.pi * FREQUENCY * n / SAMPLE_RATE),
                             np.cos(2 * np.pi * FREQUENCY * n / SAMPLE_RATE)])
    coef, *_ = np.linalg.lstsq(basis, steady, rcond=None)
    residual = steady - basis @ coef
    snr = 10 * math.log10(float(np.mean((basis @ coef) ** 2)) / max(float(np.mean(residual**2)), 1e-20))
    result["signal-to-noise (dB)"] = round(snr, 1)

    result["channels match"] = bool(np.max(np.abs(left - right)) < 2 / 32768)
    clean = (
        len(gaps) == 0
        and result["glitches"] == 0
        and abs(float(result.get("pitch (Hz)", 0)) - FREQUENCY) < 1.0
        # Turning the volume down costs 16-bit resolution, so judge noise against the
        # rounding floor at this level (about 90 dB below full level), with 10 dB to spare.
        and snr > 80 + float(result["level vs source (dB)"])
    )
    result["verdict"] = "clean" if clean else "NOT clean"
    return result


async def stream_tone(conf: BaseConfig, tone: Path, seconds: float, volume: float,
                      airplay: str) -> None:
    storage = MemoryStorage()
    settings = await storage.get_settings(conf)
    settings.protocols.raop.protocol_version = {
        "auto": AirPlayVersion.Auto, "1": AirPlayVersion.V1, "2": AirPlayVersion.V2,
    }[airplay]
    started = time.perf_counter()
    atv = await pyatv.connect(conf, asyncio.get_running_loop(), storage=storage)
    print(f"connected in {time.perf_counter() - started:.1f} s", flush=True)
    try:
        await atv.audio.set_volume(volume)
        print(f"volume set to {volume:g}%; streaming a {seconds:g} s tone "
              f"(AirPlay version: {airplay})", flush=True)
        started = time.perf_counter()
        await atv.stream.stream_file(
            str(tone), metadata=MediaMetadata(title="Tandem test tone", artist="Tandem")
        )
        total = time.perf_counter() - started
        print(f"stream finished in {total:.1f} s ({total - seconds:+.1f} s vs tone length)")
    finally:
        await asyncio.gather(*atv.close())


def scrub(text: str) -> str:
    """Mask addresses in error text (pyatv errors can include the receiver's address)."""
    return re.sub(r"\b\d{1,3}(\.\d{1,3}){3}\b", "<address>", text)


async def cmd_tone(seconds: float, volume: float, airplay: str, mode: str) -> None:
    tone = make_tone(seconds)
    print(f"starting the {mode} receiver on the Pi")
    cmd_receiver("start", mode)
    error = None
    try:
        conf = await find_receiver()
        if conf is None:
            sys.exit("expected exactly one shairport-sync receiver; stopping")
        try:
            await stream_tone(conf, tone, seconds, volume, airplay)
        except Exception as ex:  # noqa: BLE001 - a spike reports any failure and moves on
            error = f"{type(ex).__name__}: {scrub(str(ex))}"
            print(f"stream FAILED: {error}")
        await asyncio.sleep(3)  # let the receiver drain its buffer into the file
    finally:
        cmd_receiver("stop")

    tag = f"{mode}-ap{airplay}-{seconds:g}s-v{volume:g}"
    capture = STATE_DIR / f"capture-{tag}.raw"
    scp_from_pi(f"{PI_DIR}/capture.raw", capture)
    scp_from_pi(f"{PI_DIR}/receiver.log", STATE_DIR / f"receiver-{tag}.log")
    print(f"capture: {capture.stat().st_size} bytes (saved under local/spike-f/)")
    for key, value in analyse(capture.read_bytes(), seconds).items():
        print(f"  {key}: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    receiver = sub.add_parser("receiver")
    receiver.add_argument("action", choices=("start", "stop", "status"))
    receiver.add_argument("--mode", choices=MODES, default="classic")
    sub.add_parser("find")
    tone = sub.add_parser("tone")
    tone.add_argument("--seconds", type=float, default=5.0)
    tone.add_argument("--volume", type=float, default=100.0)
    tone.add_argument("--airplay", choices=("auto", "1", "2"), default="auto")
    tone.add_argument("--mode", choices=MODES, default="classic")
    args = parser.parse_args()

    if args.command == "receiver":
        cmd_receiver(args.action, args.mode)
    elif args.command == "find":
        asyncio.run(cmd_find())
    else:
        if not 0 <= args.volume <= 100:
            sys.exit("volume must be between 0 and 100")
        asyncio.run(cmd_tone(args.seconds, args.volume, args.airplay, args.mode))


if __name__ == "__main__":
    main()
