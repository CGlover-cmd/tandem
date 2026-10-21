"""Spike E: screen capture and hardware H.264 encode latency (NVENC, with AMF and x264 to compare).

Throwaway spike code (Phase 0). It answers: how fast can we grab the Windows desktop, and how
quickly can the GPU turn each frame into low-latency H.264, at 1080p30 and up to 4K60? This is
encoder groundwork only. Screen mirroring itself is shelved (ADR-0006); nothing here talks to
an AirPlay device or touches FairPlay. Findings go into docs/spikes/spike-e-encode.md.

Capture uses dxcam (DXGI Desktop Duplication). Encoding uses PyAV, which bundles FFmpeg with
h264_nvenc (NVIDIA), h264_amf (AMD) and libx264 (CPU baseline).

Privacy: no frames are written to disk and nothing that identifies the PC or its displays
(monitor names, serials) is printed. Only GPU models, resolutions, timings and sizes.

Usage (from the repo root, with the dev virtualenv's python.exe):
    python spikes/spike_e_encode.py info
    python spikes/spike_e_encode.py capture [--seconds 10]
    python spikes/spike_e_encode.py encode --encoder h264_nvenc --size 1920x1080 --fps 30
    python spikes/spike_e_encode.py encode --encoder h264_nvenc --source screen --fps 60
    python spikes/spike_e_encode.py encode --encoder h264_nvenc --source screen --scale 1920x1080
    python spikes/spike_e_encode.py gpu-path
    python spikes/spike_e_encode.py latency [--encoder h264_nvenc] [--scale 1920x1080] [--trials 20]
"""

from __future__ import annotations

import argparse
import ctypes
import gc
import os
import shutil
import statistics
import subprocess
import sys
import threading
import time
from fractions import Fraction

import av
import numpy as np

ENCODERS = ["h264_nvenc", "h264_amf", "h264_qsv", "h264_mf", "libx264", "libopenh264"]

# Low-latency settings per encoder: no B-frames, no lookahead, one packet out per frame in.
LOW_LATENCY = {
    "h264_nvenc": {"preset": "p1", "tune": "ull", "rc": "cbr", "zerolatency": "1",
                   "delay": "0", "rc-lookahead": "0"},
    "h264_amf": {"usage": "ultralowlatency", "quality": "speed", "rc": "cbr"},
    "h264_qsv": {"preset": "veryfast", "async_depth": "1", "look_ahead": "0"},
    "h264_mf": {"scenario": "display_remoting", "rate_control": "cbr", "hw_encoding": "1"},
    "libx264": {"preset": "ultrafast", "tune": "zerolatency"},
    "libopenh264": {"rc_mode": "bitrate"},
}

# Input formats we can hand over without a CPU colour conversion, best first.
PACKED_RGB = ["bgra", "bgr0"]


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def summary(label: str, ms: list[float]) -> str:
    if not ms:
        return f"{label}: no samples"
    return (f"{label}: median {statistics.median(ms):.2f} ms, p95 {pct(ms, 95):.2f} ms, "
            f"max {max(ms):.2f} ms (n={len(ms)})")


def parse_size(text: str) -> tuple[int, int]:
    w, h = text.lower().split("x")
    return int(w), int(h)


def make_dpi_aware() -> None:
    """Use physical pixels, so window positions match what desktop duplication captures."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass


# --- encoding -------------------------------------------------------------------------------


def input_format(codec_name: str) -> str:
    names = [f.name for f in av.Codec(codec_name, "w").video_formats or []]
    for fmt in PACKED_RGB:
        if fmt in names:
            return fmt
    return "nv12" if "nv12" in names else "yuv420p"


def open_encoder(name: str, width: int, height: int, fps: int, bitrate: int,
                 pix_fmt: str | None = None) -> av.VideoCodecContext:
    ctx = av.CodecContext.create(name, "w")
    ctx.width = width
    ctx.height = height
    ctx.time_base = Fraction(1, fps)
    ctx.framerate = Fraction(fps, 1)
    ctx.pix_fmt = pix_fmt or input_format(name)
    ctx.bit_rate = bitrate
    ctx.gop_size = fps * 2
    ctx.max_b_frames = 0
    ctx.options = dict(LOW_LATENCY.get(name, {}))
    ctx.open()
    return ctx


def to_frame(bgra: np.ndarray, pix_fmt: str,
             size: tuple[int, int] | None = None) -> tuple[av.VideoFrame, float]:
    """Wrap a BGRA array as a frame in the encoder's format and size (CPU, libswscale).

    Returns the frame and the time spent converting or scaling.
    """
    # from_numpy_buffer wraps the array without copying; from_ndarray copies it slowly
    # (about 36 ms for a 4K frame, versus 5.5 ms for a plain numpy copy).
    frame = av.VideoFrame.from_numpy_buffer(np.ascontiguousarray(bgra), format="bgra")
    if pix_fmt == "bgra" and (size is None or size == (frame.width, frame.height)):
        return frame, 0.0
    started = time.perf_counter()
    if size is None:
        frame = frame.reformat(format=pix_fmt)
    else:
        frame = frame.reformat(width=size[0], height=size[1], format=pix_fmt,
                               interpolation="FAST_BILINEAR")
    return frame, time.perf_counter() - started


class EncoderClock:
    """Times each frame from encode() call to the packet that carries it (matched by pts)."""

    def __init__(self, ctx: av.VideoCodecContext) -> None:
        self.ctx = ctx
        self.submitted: dict[int, float] = {}
        self.latency_ms: list[float] = []
        self.bytes = 0
        self.packets = 0
        self.keyframe_bytes: list[int] = []

    def encode(self, frame: av.VideoFrame | None, pts: int | None = None) -> list[av.Packet]:
        if frame is not None:
            frame.pts = pts
            frame.time_base = self.ctx.time_base  # ddagrab frames carry their own time base
            self.submitted[pts] = time.perf_counter()
        packets = self.ctx.encode(frame)
        now = time.perf_counter()
        for pkt in packets:
            sent = self.submitted.pop(pkt.pts, None) if pkt.pts is not None else None
            if sent is not None:
                self.latency_ms.append((now - sent) * 1000)
            self.bytes += pkt.size
            self.packets += 1
            if pkt.is_keyframe:
                self.keyframe_bytes.append(pkt.size)
        return packets


class GpuSampler:
    """Polls nvidia-smi for encoder use and the driver's own encode-latency figure."""

    FIELDS = "utilization.gpu,utilization.encoder,encoder.stats.averageFps,encoder.stats.averageLatency"

    def __init__(self) -> None:
        self.rows: list[list[str]] = []
        self.proc: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> GpuSampler:
        exe = shutil.which("nvidia-smi")
        if exe:
            self.proc = subprocess.Popen(
                [exe, f"--query-gpu={self.FIELDS}", "--format=csv,noheader,nounits", "-lms", "250"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            self.thread = threading.Thread(target=self._read, daemon=True)
            self.thread.start()
        return self

    def _read(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            self.rows.append([c.strip() for c in line.split(",")])

    def __exit__(self, *_exc: object) -> None:
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=5)

    def report(self) -> str:
        busy = [r for r in self.rows if len(r) == 4 and r[3].isdigit() and int(r[3]) > 0]
        if not busy:
            return "nvidia-smi: no NVIDIA encoder activity seen"
        gpu = statistics.mean(float(r[0]) for r in busy)
        enc = statistics.mean(float(r[1]) for r in busy)
        lat = statistics.median(int(r[3]) for r in busy) / 1000
        return (f"nvidia-smi while encoding: GPU {gpu:.0f}%, encoder {enc:.0f}%, "
                f"driver-reported encode latency median {lat:.2f} ms")


def synthetic_frames(width: int, height: int, count: int = 60) -> list[np.ndarray]:
    """Moving gradient, a sweeping bar and a noisy tile: motion and detail, like a busy screen."""
    rng = np.random.default_rng(1)
    x = np.linspace(0, 255, width, dtype=np.float32)
    y = np.linspace(0, 255, height, dtype=np.float32)[:, None]
    noise = rng.integers(0, 256, (height // 4, width // 4, 3), dtype=np.uint8)
    frames = []
    for i in range(count):
        img = np.empty((height, width, 4), dtype=np.uint8)
        img[..., 0] = ((x + i * 4) % 256).astype(np.uint8)
        img[..., 1] = ((y + i * 2) % 256).astype(np.uint8)
        img[..., 2] = (((x[None, :] + y) / 2 + i * 3) % 256).astype(np.uint8)
        img[..., 3] = 255
        bar = (i * width // count) % width
        img[:, bar:bar + width // 20, :3] = 255
        ty, tx = (i * 7) % (height - height // 4), (i * 11) % (width - width // 4)
        img[ty:ty + height // 4, tx:tx + width // 4, :3] = np.roll(noise, i, axis=1)
        frames.append(img)
    return frames


# --- capture --------------------------------------------------------------------------------


def open_camera():
    """Open desktop duplication on whichever GPU drives the main display."""
    import dxcam

    errors = []
    for device in range(4):
        try:
            return dxcam.create(device_idx=device, output_idx=0, output_color="BGRA"), device
        except Exception as exc:  # noqa: BLE001 - spike: report and try the next adapter
            errors.append(f"adapter {device}: {type(exc).__name__}")
    raise RuntimeError("no adapter with a display output: " + "; ".join(errors))


def adapter_names() -> list[str]:
    """GPU model names from dxcam's device list (models only, no display or monitor names)."""
    import dxcam

    names = []
    for line in dxcam.device_info().splitlines():
        if "Name:" in line:
            names.append(line.split("Name:", 1)[1].split("Dedicated")[0].strip(" ,"))
    return names


class Animator:
    """A small always-on-top window that keeps the screen changing, or flips a colour patch."""

    def __init__(self, size: int = 240) -> None:
        import tkinter as tk

        self.tk = tk
        self.root = tk.Tk()
        self.root.title("Tandem Spike E")
        self.root.attributes("-topmost", True)
        self.root.geometry(f"{size}x{size}+120+120")
        self.canvas = tk.Canvas(self.root, width=size, height=size, highlightthickness=0, bg="black")
        self.canvas.pack()
        self.size = size
        self.bar = self.canvas.create_rectangle(0, 0, 20, size, fill="white", width=0)
        self.pos = 0
        self.root.update()

    def centre(self) -> tuple[int, int]:
        return (self.canvas.winfo_rootx() + self.size // 2, self.canvas.winfo_rooty() + self.size // 2)

    def step(self) -> None:
        self.pos = (self.pos + 7) % self.size
        self.canvas.coords(self.bar, self.pos, 0, self.pos + 20, self.size)
        self.root.update()

    def fill(self, colour: str) -> None:
        self.canvas.itemconfigure(self.bar, state="hidden")
        self.canvas.configure(bg=colour)
        self.root.update()

    def close(self) -> None:
        self.root.destroy()


# --- commands -------------------------------------------------------------------------------


def cmd_info(_args: argparse.Namespace) -> int:
    print(f"PyAV {av.__version__}, FFmpeg libavcodec {av.library_versions['libavcodec']}")
    for name in ENCODERS:
        try:
            codec = av.Codec(name, "w")
        except av.codec.codec.UnknownCodecError:
            print(f"  {name:12s} not in this FFmpeg build")
            continue
        try:
            open_encoder(name, 1920, 1080, 30, 8_000_000)
            fmts = ", ".join(f.name for f in codec.video_formats or [])
            print(f"  {name:12s} opens at 1080p30; input {input_format(name)}  (accepts: {fmts})")
        except Exception as exc:  # noqa: BLE001
            print(f"  {name:12s} in build but does not open: {str(exc).splitlines()[0][:90]}")
    try:
        print("GPUs: " + "; ".join(adapter_names()))
        cam, device = open_camera()
        frame = None
        for _ in range(50):
            frame = cam.grab()
            if frame is not None:
                break
            time.sleep(0.02)
        print(f"main display: on adapter {device}, {cam.width}x{cam.height}"
              + ("" if frame is None else f", frames arrive as {frame.shape[1]}x{frame.shape[0]} BGRA"))
    except Exception as exc:  # noqa: BLE001
        print(f"capture: {type(exc).__name__}: {exc}")
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    """Grab the desktop as fast as it changes, while a small window animates."""
    make_dpi_aware()
    anim = Animator()
    cam, device = open_camera()
    print(f"capturing {cam.width}x{cam.height} on adapter {device} for {args.seconds:.0f} s")
    grab_ms: list[float] = []
    arrivals: list[float] = []
    misses = 0
    cpu0, wall0 = time.process_time(), time.perf_counter()
    end = wall0 + args.seconds
    while time.perf_counter() < end:
        anim.step()
        t0 = time.perf_counter()
        frame = cam.grab()
        t1 = time.perf_counter()
        if frame is None:
            misses += 1
            continue
        grab_ms.append((t1 - t0) * 1000)
        arrivals.append(t1)
    wall = time.perf_counter() - wall0
    cpu = time.process_time() - cpu0
    anim.close()
    gaps = [(b - a) * 1000 for a, b in zip(arrivals, arrivals[1:])]
    print(f"new frames: {len(grab_ms)} in {wall:.1f} s = {len(grab_ms) / wall:.1f} fps "
          f"(empty polls: {misses})")
    print(summary("grab() with a new frame (GPU -> CPU copy)", grab_ms))
    print(summary("gap between new frames", gaps))
    print(f"CPU (this process, incl. the animation): {cpu / wall * 100:.0f}% of one core")
    return 0


def cmd_encode(args: argparse.Namespace) -> int:
    """Encode paced frames in real time and time each frame through the encoder."""
    make_dpi_aware()
    cam = None
    anim = None
    if args.source == "screen":
        anim = Animator()
        cam, device = open_camera()
        width, height = parse_size(args.scale) if args.scale else (cam.width, cam.height)
        print(f"source: live desktop {cam.width}x{cam.height} (adapter {device}), "
              f"encoded at {width}x{height}")
    else:
        width, height = parse_size(args.size)
        frames = synthetic_frames(width, height)
        print(f"source: synthetic {width}x{height}, {len(frames)} distinct frames")
    bitrate = args.bitrate or int(width * height * args.fps * 0.1)
    ctx = open_encoder(args.encoder, width, height, args.fps, bitrate)
    clock = EncoderClock(ctx)
    print(f"encoder {args.encoder}, input {ctx.pix_fmt}, {args.fps} fps, target {bitrate / 1e6:.1f} Mbit/s, "
          f"pace: {'real time' if not args.flat_out else 'as fast as possible'}")

    convert_ms: list[float] = []
    wrap_ms: list[float] = []
    total = int(args.seconds * args.fps)
    late = 0
    last = None
    with GpuSampler() as gpu:
        cpu0, wall0 = time.process_time(), time.perf_counter()
        for i in range(total):
            due = wall0 + i / args.fps
            if not args.flat_out:
                delay = due - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                elif delay < -1 / args.fps:
                    late += 1
            if cam is not None:
                anim.step()
                grabbed = cam.grab()
                if grabbed is not None:
                    last = grabbed
                if last is None:
                    continue
                src = last
            else:
                src = frames[i % len(frames)]
            t0 = time.perf_counter()
            frame, conv = to_frame(src, ctx.pix_fmt, (width, height))
            wrap_ms.append((time.perf_counter() - t0 - conv) * 1000)
            convert_ms.append(conv * 1000)
            clock.encode(frame, pts=i)
        clock.encode(None)
        wall = time.perf_counter() - wall0
        cpu = time.process_time() - cpu0
    if cam is not None:
        anim.close()

    print(f"frames: {total} in {wall:.2f} s = {total / wall:.1f} fps; packets {clock.packets}; "
          f"late slots: {late}")
    print(summary("encode latency (frame in -> packet out)", clock.latency_ms))
    print(summary("wrap array as frame", wrap_ms))
    if any(convert_ms):
        print(summary(f"CPU scale/convert to {width}x{height} {ctx.pix_fmt}", convert_ms))
    mbit = clock.bytes * 8 / (total / args.fps) / 1e6
    key = statistics.median(clock.keyframe_bytes) / 1024 if clock.keyframe_bytes else 0
    print(f"output: {mbit:.1f} Mbit/s, keyframes {len(clock.keyframe_bytes)} (median {key:.0f} KiB)")
    print(f"CPU (this process): {cpu / wall * 100:.0f}% of one core")
    print(gpu.report())
    return 0


def ddagrab_graph(*chain: tuple[str, str]):
    """FFmpeg's own desktop duplication source (ddagrab), which yields D3D11 GPU frames."""
    import av.filter

    graph = av.filter.Graph()
    nodes = [graph.add("ddagrab", "output_idx=0:framerate=60:draw_mouse=0:dup_frames=1")]
    nodes += [graph.add(name, opts) for name, opts in chain]
    nodes.append(graph.add("buffersink"))
    for a, b in zip(nodes, nodes[1:]):
        a.link_to(b)
    graph.configure()
    return graph, nodes[-1]


def cmd_gpu_path(args: argparse.Namespace) -> int:
    """Can D3D11 frames go straight into NVENC through PyAV? And how fast is ddagrab via memory?"""
    _graph, sink = ddagrab_graph()
    frame = sink.pull()
    print(f"ddagrab frame: {frame.width}x{frame.height}, format {frame.format.name} (on the GPU)")
    try:
        open_encoder("h264_nvenc", frame.width, frame.height, 60, 40_000_000, pix_fmt="d3d11")
        print("NVENC opened with D3D11 input")
    except Exception as exc:  # noqa: BLE001
        print(f"NVENC with D3D11 input: does not open ({type(exc).__name__}); PyAV cannot hand "
              "the encoder the frames' GPU context (hw_frames_ctx)")
    try:
        ddagrab_graph(("scale_d3d11", "width=1920:height=1080:format=nv12"))
        print("GPU scaling (scale_d3d11): works")
    except Exception as exc:  # noqa: BLE001
        print(f"GPU scaling (scale_d3d11): fails ({type(exc).__name__})")

    # Only one duplication session at a time: free the first graph before opening the next.
    del _graph, sink, frame
    gc.collect()
    _graph, sink = ddagrab_graph(("hwdownload", ""), ("format", "bgra"))
    frame = sink.pull()
    ctx = open_encoder("h264_nvenc", frame.width, frame.height, 60,
                       int(frame.width * frame.height * 60 * 0.1))
    clock = EncoderClock(ctx)
    pull_ms: list[float] = []
    started = time.perf_counter()
    for i in range(args.frames):
        t0 = time.perf_counter()
        frame = sink.pull()
        pull_ms.append((time.perf_counter() - t0) * 1000)
        clock.encode(frame, pts=i)
    wall = time.perf_counter() - started
    print(f"ddagrab -> main memory -> NVENC: {args.frames / wall:.1f} fps")
    print(summary("ddagrab + download per frame", pull_ms))
    print(summary("encode latency", clock.latency_ms))
    return 0


def colour_of(frame: np.ndarray, x: int, y: int) -> str:
    b, g, r = (int(v) for v in frame[y, x, :3])
    if r > 180 and g < 80 and b < 80:
        return "red"
    if b > 180 and r < 80 and g < 80:
        return "blue"
    return "other"


def cmd_latency(args: argparse.Namespace) -> int:
    """Change a patch on screen, then time: until capture sees it, encode, and decode back."""
    make_dpi_aware()
    anim = Animator()
    cam, device = open_camera()
    cx, cy = anim.centre()
    width, height = parse_size(args.scale) if args.scale else (cam.width, cam.height)
    size = (width, height)
    dx, dy = cx * width // cam.width, cy * height // cam.height
    ctx = open_encoder(args.encoder, width, height, args.fps, int(width * height * args.fps * 0.1))
    clock = EncoderClock(ctx)
    decoder = av.CodecContext.create("h264", "r")
    print(f"display {cam.width}x{cam.height} on adapter {device}, encoded at {width}x{height}; encoder {args.encoder} ({ctx.pix_fmt}); "
          f"{args.trials} trials")

    seen_ms: list[float] = []
    enc_ms: list[float] = []
    dec_ms: list[float] = []
    glass_ms: list[float] = []
    mismatches = 0
    pts = 0
    # Warm up: the first frames include the keyframe and encoder start-up.
    for _ in range(10):
        anim.fill("black")
        f = cam.grab()
        if f is not None:
            frame, _ = to_frame(f, ctx.pix_fmt, size)
            for pkt in clock.encode(frame, pts=pts):
                decoder.decode(pkt)
            pts += 1
        time.sleep(0.03)
    clock.latency_ms.clear()

    for trial in range(args.trials):
        colour = "red" if trial % 2 == 0 else "blue"
        anim.fill("#ff0000" if colour == "red" else "#0000ff")
        changed = time.perf_counter()
        frame_np = None
        while time.perf_counter() - changed < 1.0:
            f = cam.grab()
            if f is not None and colour_of(f, cx, cy) == colour:
                frame_np = f
                break
        seen = time.perf_counter()
        if frame_np is None:
            print(f"  trial {trial + 1}: change not captured within 1 s")
            continue
        frame, _ = to_frame(frame_np, ctx.pix_fmt, size)
        before = len(clock.latency_ms)
        packets = clock.encode(frame, pts=pts)
        pts += 1
        encoded = time.perf_counter()
        decoded_frames = []
        for pkt in packets:
            decoded_frames += decoder.decode(pkt)
        done = time.perf_counter()
        if not decoded_frames or len(clock.latency_ms) == before:
            print(f"  trial {trial + 1}: encoder held the frame back (no packet yet)")
            continue
        back = decoded_frames[-1].to_ndarray(format="bgra")
        if colour_of(back, dx, dy) != colour:
            mismatches += 1
        seen_ms.append((seen - changed) * 1000)
        enc_ms.append((encoded - seen) * 1000)
        dec_ms.append((done - encoded) * 1000)
        glass_ms.append((done - changed) * 1000)
        time.sleep(0.1 + (trial % 3) * 0.017)  # vary the phase against the display refresh
    anim.close()

    print(summary("screen change -> captured frame", seen_ms))
    print(summary("wrap + scale/convert + encode (frame -> packet)", enc_ms))
    print(summary("software decode (packet -> picture)", dec_ms))
    print(summary("total: change -> decoded picture on this PC", glass_ms))
    print(f"decoded colour wrong in {mismatches} of {len(glass_ms)} trials")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    p = sub.add_parser("capture")
    p.add_argument("--seconds", type=float, default=10)
    p = sub.add_parser("encode")
    p.add_argument("--encoder", default="h264_nvenc")
    p.add_argument("--source", choices=["synthetic", "screen"], default="synthetic")
    p.add_argument("--size", default="1920x1080")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--seconds", type=float, default=10)
    p.add_argument("--bitrate", type=int, default=0, help="bits/s; default 0.1 bit per pixel")
    p.add_argument("--flat-out", action="store_true", help="no pacing: measure peak throughput")
    p.add_argument("--scale", default="", help="screen source: encode at WxH (CPU scaling)")
    p = sub.add_parser("gpu-path")
    p.add_argument("--frames", type=int, default=120)
    p = sub.add_parser("latency")
    p.add_argument("--encoder", default="h264_nvenc")
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--trials", type=int, default=20)
    p.add_argument("--scale", default="", help="encode at WxH (CPU scaling)")
    args = parser.parse_args()
    return {"info": cmd_info, "capture": cmd_capture, "encode": cmd_encode,
            "gpu-path": cmd_gpu_path, "latency": cmd_latency}[args.cmd](args)


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    # Skip interpreter teardown. dxcam's release() and comtypes' COM finalizers crash with an
    # access violation (dxcam 0.3.0), so cameras are never released and the process just ends.
    os._exit(code)
