"""Spike C: capture what Windows is playing (WASAPI loopback).

Throwaway spike code (Phase 0). It answers: can we capture the PC's own audio from Python, in
what format, how fast, at what CPU cost, and does capture survive silence and muting?
Findings go into docs/spikes/spike-c-loopback.md.

It uses miniaudio, which pyatv already depends on. The Python wrapper only offers plain
capture, so LoopbackDevice below repeats its setup with miniaudio's loopback device type.

Privacy: nothing that identifies a device (name, identifier) is printed, and no captured audio
is written to disk. Only counts, timings and levels are reported.

Usage (from the repo root, with the dev virtualenv's python.exe):
    python spikes/spike_c_loopback.py info
    python spikes/spike_c_loopback.py latency [--clicks 10]
    python spikes/spike_c_loopback.py capture [--seconds 60]
    python spikes/spike_c_loopback.py level [--seconds 3]
"""

from __future__ import annotations

import argparse
import array
import math
import statistics
import sys
import threading
import time

import miniaudio
from _miniaudio import ffi, lib
from miniaudio import Backend, SampleFormat

BACKENDS = [Backend.WASAPI]
FORMAT_NAMES = {
    lib.ma_format_u8: "8-bit unsigned",
    lib.ma_format_s16: "16-bit signed",
    lib.ma_format_s24: "24-bit signed",
    lib.ma_format_s32: "32-bit signed",
    lib.ma_format_f32: "32-bit float",
}


class LoopbackDevice(miniaudio.CaptureDevice):
    """miniaudio's CaptureDevice, opened in loopback mode on the default output.

    sample_rate=0 keeps the output's own rate, so miniaudio does no resampling.
    """

    def __init__(self, sample_rate: int = 0, period_msec: int = 10) -> None:
        miniaudio.AbstractDevice.__init__(self)
        self.format = SampleFormat.FLOAT32
        self.sample_width = 4
        self.nchannels = 2
        self.buffersize_msec = period_msec
        self._ffi_handle = ffi.new_handle(self)
        self._devconfig = lib.ma_device_config_init(lib.ma_device_type_loopback)
        self._devconfig.sampleRate = sample_rate
        self._devconfig.capture.channels = self.nchannels
        self._devconfig.capture.format = self.format.value
        self._devconfig.capture.pDeviceID = ffi.NULL  # NULL = the default output
        self._devconfig.periodSizeInMilliseconds = period_msec
        self._devconfig.pUserData = self._ffi_handle
        self._devconfig.dataCallback = lib._internal_data_callback
        self._devconfig.stopCallback = lib._internal_stop_callback
        self.callback_generator = None
        self._context = self._make_context(BACKENDS)
        result = lib.ma_device_init(self._context, ffi.addressof(self._devconfig), self._device)
        if result != lib.MA_SUCCESS:
            raise miniaudio.MiniaudioError("failed to open loopback capture", result)
        self.sample_rate = self._device.sampleRate
        self.backend = ffi.string(lib.ma_get_backend_name(self._device.pContext.backend)).decode()


def default_output_formats() -> list[str]:
    """The default output's native formats, as reported by WASAPI (no name or identifier)."""
    context = ffi.new("ma_context*")
    backends = ffi.new("ma_backend[]", [Backend.WASAPI.value])
    if lib.ma_context_init(backends, 1, ffi.NULL, context) != lib.MA_SUCCESS:
        raise miniaudio.MiniaudioError("cannot open WASAPI")
    try:
        info = ffi.new("ma_device_info*")
        if (
            lib.ma_context_get_device_info(context, lib.ma_device_type_playback, ffi.NULL, info)
            != lib.MA_SUCCESS
        ):
            raise miniaudio.MiniaudioError("cannot read the default output")
        formats = []
        for i in range(info.nativeDataFormatCount):
            f = info.nativeDataFormats[i]
            name = FORMAT_NAMES.get(f.format, f"format {f.format}")
            formats.append(f"{name}, {f.sampleRate} Hz, {f.channels} ch")
        return formats
    finally:
        lib.ma_context_uninit(context)


class Recorder:
    """Collects loopback callbacks: arrival times, frame counts and (optionally) the audio."""

    def __init__(self, keep_audio: bool) -> None:
        self.keep_audio = keep_audio
        self.audio = bytearray()
        self.calls: list[tuple[float, int]] = []
        self.on_block = None  # optional hook: (arrival_time, samples) -> None

    def generator(self):
        while True:
            data = yield
            now = time.perf_counter()
            frames = len(data) // 8
            self.calls.append((now, frames))
            if self.keep_audio:
                self.audio += data
            if self.on_block is not None:
                self.on_block(now, array.array("f", bytes(data)))


def dbfs(value: float) -> str:
    return "-inf dBFS" if value <= 0 else f"{20 * math.log10(value):.1f} dBFS"


def cmd_info(_args: argparse.Namespace) -> int:
    print(f"loopback supported by WASAPI: {miniaudio.is_loopback_supported(Backend.WASAPI)}")
    outputs = miniaudio.Devices(backends=BACKENDS).get_playbacks()
    print(f"output devices: {len(outputs)}")
    print("default output native formats:")
    for line in default_output_formats():
        print(f"  {line}")
    started = time.perf_counter()
    with LoopbackDevice() as dev:
        opened = time.perf_counter() - started
        print(f"loopback opened in {opened * 1000:.0f} ms, backend {dev.backend}, "
              f"{dev.sample_rate} Hz, delivered as 32-bit float stereo")
    return 0


def cmd_latency(args: argparse.Namespace) -> int:
    """Play short clicks through the default output and time how soon loopback returns them."""
    rate = 48000
    with LoopbackDevice() as probe:
        rate = probe.sample_rate
    interval = int(rate * 0.5)
    click_len = int(rate * 0.002)
    writes: list[float] = []
    hits: list[float] = []
    state = {"pos": 0, "last_hit": 0.0}
    done = threading.Event()

    def player():
        frames = yield b""
        while True:
            now = time.perf_counter()
            buf = array.array("f", bytes(frames * 8))
            start = state["pos"]
            for n in range(frames):
                p = start + n
                click = p // interval
                if 1 <= click <= args.clicks and p % interval < click_len:
                    if p % interval == 0:
                        writes.append(now + n / rate)
                    buf[2 * n] = buf[2 * n + 1] = 0.5
            state["pos"] = start + frames
            if state["pos"] > (args.clicks + 0.5) * interval:
                done.set()
            frames = yield buf

    def on_block(arrival: float, samples: array.array) -> None:
        n = len(samples) // 2
        for i in range(n):
            if abs(samples[2 * i]) > args.threshold:
                t = arrival - (n - i) / rate
                if t - state["last_hit"] > 0.25:
                    hits.append(t)
                    state["last_hit"] = t
                break

    rec = Recorder(keep_audio=False)
    rec.on_block = on_block
    with LoopbackDevice(period_msec=10) as cap, miniaudio.PlaybackDevice(
        output_format=SampleFormat.FLOAT32, nchannels=2, sample_rate=rate,
        buffersize_msec=10, backends=BACKENDS,
    ) as play:
        gen_cap = rec.generator()
        next(gen_cap)
        cap.start(gen_cap)
        gen_play = player()
        next(gen_play)
        play.start(gen_play)
        done.wait(timeout=args.clicks * 0.5 + 5)
        time.sleep(0.5)
    delays = []
    for w in writes:
        later = [h for h in hits if h >= w - 0.005]
        if later and later[0] - w < 0.4:
            delays.append((later[0] - w) * 1000)
    print(f"clicks played: {len(writes)}, heard by loopback: {len(delays)}, "
          f"extra detections: {max(0, len(hits) - len(delays))}")
    if delays:
        print(f"playback write -> loopback delivery: median {statistics.median(delays):.1f} ms, "
              f"min {min(delays):.1f} ms, max {max(delays):.1f} ms")
        print("  (includes our own 10 ms playback buffer and the Windows mixer)")
    frames = [f for _, f in rec.calls]
    if frames:
        print(f"loopback block size: median {statistics.median(frames):.0f} frames "
              f"({statistics.median(frames) / rate * 1000:.1f} ms)")
    return 0 if delays else 1


def cmd_capture(args: argparse.Namespace) -> int:
    """Capture for a while; report delivery, gaps, levels, CPU and conversion cost."""
    rec = Recorder(keep_audio=True)
    with LoopbackDevice(period_msec=10) as dev:
        rate = dev.sample_rate
        gen = rec.generator()
        next(gen)
        cpu0, wall0 = time.process_time(), time.perf_counter()
        dev.start(gen)
        time.sleep(args.seconds)
        cpu1, wall1 = time.process_time(), time.perf_counter()
    elapsed = wall1 - wall0
    frames = sum(f for _, f in rec.calls)
    expected = rate * elapsed
    print(f"captured {elapsed:.1f} s at {rate} Hz: {len(rec.calls)} blocks, "
          f"{frames / expected * 100:.1f}% of expected frames")
    if rec.calls:
        first = rec.calls[0][0] - wall0
        gaps = [b[0] - a[0] for a, b in zip(rec.calls, rec.calls[1:])]
        print(f"first block after {first * 1000:.0f} ms; "
              f"longest gap between blocks {max(gaps, default=0) * 1000:.0f} ms")
    print(f"process CPU while capturing: {(cpu1 - cpu0) / elapsed * 100:.1f}% of one core")

    samples = array.array("f", bytes(rec.audio))
    per_second = rate * 2
    silent = loud = 0
    for start in range(0, len(samples), per_second):
        chunk = samples[start:start + per_second]
        peak = max((abs(s) for s in chunk), default=0.0)
        if peak < 1e-4:
            silent += 1
        else:
            loud += 1
    peak_all = max((abs(s) for s in samples), default=0.0)
    print(f"seconds with sound: {loud}, silent: {silent}; overall peak {dbfs(peak_all)}")

    if rec.audio:
        started = time.perf_counter()
        out = miniaudio.convert_frames(
            SampleFormat.FLOAT32, 2, rate, bytes(rec.audio), SampleFormat.SIGNED16, 2, 44100
        )
        cost = time.perf_counter() - started
        audio_secs = len(rec.audio) / 8 / rate
        print(f"convert {audio_secs:.1f} s to 44.1 kHz/16-bit: {cost * 1000:.0f} ms "
              f"({cost / audio_secs * 100:.2f}% of real time), {len(out)} bytes out")
    return 0


def cmd_level(args: argparse.Namespace) -> int:
    """Play a steady tone at a known level and measure what loopback receives."""
    amplitude = 0.25
    rec = Recorder(keep_audio=True)
    with LoopbackDevice(period_msec=10) as cap:
        rate = cap.sample_rate

        def tone():
            pos = 0
            frames = yield b""
            while True:
                buf = array.array("f", bytes(frames * 8))
                for n in range(frames):
                    s = amplitude * math.sin(2 * math.pi * 440 * (pos + n) / rate)
                    buf[2 * n] = buf[2 * n + 1] = s
                pos += frames
                frames = yield buf

        with miniaudio.PlaybackDevice(
            output_format=SampleFormat.FLOAT32, nchannels=2, sample_rate=rate,
            buffersize_msec=20, backends=BACKENDS,
        ) as play:
            gen = rec.generator()
            next(gen)
            cap.start(gen)
            gen_tone = tone()
            next(gen_tone)
            play.start(gen_tone)
            time.sleep(args.seconds)
    samples = array.array("f", bytes(rec.audio))
    # Skip the first half second while the tone starts.
    body = samples[rate:] if len(samples) > rate * 2 else samples
    rms = math.sqrt(sum(s * s for s in body) / len(body)) if body else 0.0
    played_rms = amplitude / math.sqrt(2)
    print(f"tone played at {dbfs(played_rms)} RMS; loopback received {dbfs(rms)} RMS "
          f"({len(rec.calls)} blocks)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info")
    p = sub.add_parser("latency")
    p.add_argument("--clicks", type=int, default=10)
    p.add_argument("--threshold", type=float, default=0.05)
    p = sub.add_parser("capture")
    p.add_argument("--seconds", type=float, default=60)
    p = sub.add_parser("level")
    p.add_argument("--seconds", type=float, default=3)
    args = parser.parse_args()
    handler = {"info": cmd_info, "latency": cmd_latency, "capture": cmd_capture,
               "level": cmd_level}[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
