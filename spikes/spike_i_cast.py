"""Spike I: cast the PC's screen to an Apple TV as a live HLS stream (no FairPlay).

Throwaway spike code. It answers: can Tandem show the PC's screen on an Apple TV using only
the "play this URL" request the TV already accepts (Phase 7), and how far behind is it?
The pipeline: desktop duplication (dxcam) -> scale to the chosen size -> H.264 (NVENC, then
Media Foundation, then x264) plus the PC's audio (process loopback, ADR-0020) as AAC -> an
HLS playlist with short segments -> a small web server on the home network -> the TV plays
the playlist's address. This is not screen mirroring (ADR-0006): the TV plays an ordinary
video stream, and nothing here touches FairPlay.

Privacy: the TV is chosen by model, never by name; no names, addresses or identifiers are
printed. The stream address (it holds the PC's address) is never printed. Segments are written
to a temporary folder and deleted at the end. Results go to local/spike-i/ (git-ignored).

Usage (from the repo root, with the spike venv's python.exe):
    python spikes/spike_i_cast.py pair                         # AirPlay PIN (from --pin-file)
    python spikes/spike_i_cast.py local --seconds 10           # encode only, no TV
    python spikes/spike_i_cast.py cast --seconds 120           # cast to the Apple TV
    python spikes/spike_i_cast.py cast --seconds 600 --clock   # 10 minutes, with a clock window
Options: --encoder auto|h264_nvenc|h264_mf|libx264, --size 1920x1080, --fps 30,
--segment 1.0, --list-size 6, --start-offset -2.0 (EXT-X-START), --bitrate 8000000,
--source desktop|pattern, --no-audio, --storage <pyatv storage file>.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import secrets
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "local" / "spike-i"
SAMPLE_RATE = 44100

LOW_LATENCY = {
    "h264_nvenc": {"preset": "p1", "tune": "ull", "rc": "cbr", "zerolatency": "1",
                   "delay": "0", "rc-lookahead": "0", "forced-idr": "1"},
    "h264_mf": {"scenario": "display_remoting", "rate_control": "cbr", "hw_encoding": "1"},
    "libx264": {"preset": "ultrafast", "tune": "zerolatency"},
}
ENCODER_ORDER = ["h264_nvenc", "h264_mf", "libx264"]


def make_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


# --- encoder ---------------------------------------------------------------------------------


def encoder_opens(name: str, width: int, height: int, fps: int) -> bool:
    try:
        ctx = av.CodecContext.create(name, "w")
        ctx.width, ctx.height = width, height
        ctx.time_base = Fraction(1, fps)
        ctx.pix_fmt = "nv12" if name != "libx264" else "yuv420p"
        ctx.options = dict(LOW_LATENCY.get(name, {}))
        ctx.open()
        return True
    except Exception:
        return False


def pick_encoder(wanted: str, width: int, height: int, fps: int) -> str:
    names = ENCODER_ORDER if wanted == "auto" else [wanted]
    for name in names:
        if encoder_opens(name, width, height, fps):
            return name
    raise SystemExit("no H.264 encoder opened")


class HlsWriter:
    """Encodes frames and PCM into an HLS playlist with short segments, in a folder."""

    def __init__(self, folder: Path, *, encoder: str, size: tuple[int, int], fps: int,
                 bitrate: int, segment: float, list_size: int, audio: bool,
                 segment_type: str = "mpegts") -> None:
        self.folder = folder
        self.fps = fps
        self.size = size
        flags = ["independent_segments", "program_date_time"]
        if list_size:
            flags.append("delete_segments")
        options = {
            "hls_time": str(segment),
            "hls_list_size": str(list_size),
            "hls_flags": "+".join(flags),
            "hls_segment_type": segment_type,
        }
        if not list_size:
            options["hls_playlist_type"] = "event"
        if segment_type == "fmp4":
            options["hls_fmp4_init_filename"] = "init.mp4"
        self.container = av.open(str(folder / "index.m3u8"), mode="w", format="hls",
                                 options=options)
        v = self.container.add_stream(encoder, rate=fps)
        v.width, v.height = size
        v.pix_fmt = "nv12" if encoder != "libx264" else "yuv420p"
        v.time_base = Fraction(1, 90000)
        v.bit_rate = bitrate
        cc = v.codec_context
        cc.gop_size = max(1, round(fps * segment))  # a keyframe starts every segment
        cc.max_b_frames = 0
        opts = dict(LOW_LATENCY.get(encoder, {}))
        if encoder == "libx264":
            opts["x264-params"] = f"keyint={cc.gop_size}:min-keyint={cc.gop_size}:scenecut=0"
        cc.options = opts
        self.video = v
        self.audio = None
        if audio:
            a = self.container.add_stream("aac", rate=SAMPLE_RATE)
            a.layout = "stereo"
            a.time_base = Fraction(1, SAMPLE_RATE)
            a.bit_rate = 128_000
            self.audio = a
        self.audio_pts = 0
        self.lock = threading.Lock()

    def add_video(self, frame: av.VideoFrame, seconds: float) -> None:
        frame.pts = round(seconds * 90000)
        frame.time_base = self.video.time_base
        frame.pict_type = av.video.frame.PictureType.NONE
        with self.lock:
            for packet in self.video.encode(frame):
                self.container.mux(packet)

    def add_audio(self, pcm: np.ndarray) -> None:
        """Interleaved s16 stereo samples, shape (1, n*2)."""
        if self.audio is None or pcm.size == 0:
            return
        frame = av.AudioFrame.from_ndarray(pcm, format="s16", layout="stereo")
        frame.sample_rate = SAMPLE_RATE
        frame.pts = None  # sequential: audio is paced by sample count from the start
        frame.time_base = self.audio.time_base
        self.audio_pts += pcm.size // 2
        with self.lock:
            for packet in self.audio.encode(frame):
                self.container.mux(packet)

    def close(self) -> None:
        with self.lock:
            for stream in (self.video, self.audio):
                if stream is not None:
                    for packet in stream.encode():
                        self.container.mux(packet)
            self.container.close()


# --- sources ---------------------------------------------------------------------------------


class DesktopSource:
    def __init__(self, fps: int) -> None:
        import dxcam

        self.camera = None
        for device in range(4):
            try:
                self.camera = dxcam.create(device_idx=device, output_idx=0, output_color="BGRA")
                break
            except Exception:
                continue
        if self.camera is None:
            raise SystemExit("desktop duplication didn't open")
        self.camera.start(target_fps=fps, video_mode=True)

    def frame(self) -> np.ndarray:
        return self.camera.get_latest_frame()


class PatternSource:
    def __init__(self, size: tuple[int, int]) -> None:
        self.w, self.h = size
        self.i = 0

    def frame(self) -> np.ndarray:
        img = np.zeros((self.h, self.w, 4), np.uint8)
        x = (self.i * 12) % self.w
        img[:, x:x + 48, :3] = 255
        self.i += 1
        return img


class AudioFeed:
    """The PC's audio from process loopback, paced to the stream clock; silence fills gaps."""

    def __init__(self) -> None:
        from tandem.engine.adapters.process_loopback import CaptureMode, SystemCapture

        self.buffer: deque[bytes] = deque()
        self.held = 0
        self.lock = threading.Lock()
        self.capture = SystemCapture(CaptureMode())
        self.dropped = 0
        self.padded = 0
        self.capture.start(self._on_pcm)

    def _on_pcm(self, data: bytes) -> None:
        with self.lock:
            self.buffer.append(data)
            self.held += len(data)
            limit = SAMPLE_RATE * 4 // 5  # 200 ms; drop the oldest past that (clock drift)
            while self.held > limit and self.buffer:
                old = self.buffer.popleft()
                self.held -= len(old)
                self.dropped += len(old)

    def take(self, samples: int) -> np.ndarray:
        want = samples * 4
        out = bytearray()
        with self.lock:
            while len(out) < want and self.buffer:
                chunk = self.buffer.popleft()
                need = want - len(out)
                out += chunk[:need]
                if len(chunk) > need:
                    self.buffer.appendleft(chunk[need:])
                self.held -= min(len(chunk), need)
        if len(out) < want:
            self.padded += want - len(out)
            out += bytes(want - len(out))
        return np.frombuffer(bytes(out), np.int16).reshape(1, -1)

    def stop(self) -> None:
        self.capture.stop()


# --- the encode loop ---------------------------------------------------------------------------


class Caster:
    def __init__(self, args: argparse.Namespace, folder: Path) -> None:
        self.args = args
        self.size = tuple(int(x) for x in args.size.lower().split("x"))
        self.encoder = pick_encoder(args.encoder, *self.size, args.fps)
        self.writer = HlsWriter(folder, encoder=self.encoder, size=self.size, fps=args.fps,
                                bitrate=args.bitrate, segment=args.segment,
                                list_size=args.list_size, audio=not args.no_audio,
                                segment_type=args.segment_type)
        self.source = DesktopSource(args.fps) if args.source == "desktop" else PatternSource(self.size)
        self.audio = None if args.no_audio else AudioFeed()
        self.stop_flag = threading.Event()
        self.t0 = 0.0
        self.t0_wall = 0.0
        self.frame_ms: list[float] = []
        self.late = 0
        self.frames = 0
        self.thread = threading.Thread(target=self._run, name="cast-encode", daemon=True)

    def start(self) -> None:
        self.t0 = time.perf_counter()
        self.t0_wall = time.time()
        self.thread.start()

    def media_now(self) -> float:
        return time.perf_counter() - self.t0

    def _run(self) -> None:
        period = 1 / self.args.fps
        next_tick = self.t0
        while not self.stop_flag.is_set():
            now = time.perf_counter()
            if now < next_tick:
                time.sleep(next_tick - now)
            elif now - next_tick > period:
                self.late += 1
                next_tick = now
            started = time.perf_counter()
            raw = self.source.frame()
            frame = av.VideoFrame.from_numpy_buffer(np.ascontiguousarray(raw), format="bgra")
            frame = frame.reformat(width=self.size[0], height=self.size[1],
                                   format=self.writer.video.pix_fmt,
                                   interpolation="FAST_BILINEAR")
            t = started - self.t0
            self.writer.add_video(frame, t)
            if self.audio is not None:
                due = round((time.perf_counter() - self.t0) * SAMPLE_RATE) - self.writer.audio_pts
                if due > 0:
                    self.writer.add_audio(self.audio.take(due))
            self.frame_ms.append((time.perf_counter() - started) * 1000)
            self.frames += 1
            next_tick += period

    def stop(self) -> None:
        self.stop_flag.set()
        self.thread.join(timeout=5)
        if self.audio is not None:
            self.audio.stop()
        self.writer.close()


# --- web server ---------------------------------------------------------------------------------


class Server:
    """Serves the HLS folder under a random path; logs when each file was asked for."""

    def __init__(self, folder: Path, host: str, start_offset: float | None) -> None:
        self.folder = folder
        self.host = host
        self.token = secrets.token_urlsafe(18)
        self.start_offset = start_offset
        self.requests: list[tuple[float, str]] = []
        self.runner = None
        self.port = 0

    async def start(self) -> None:
        from aiohttp import web

        app = web.Application()
        app.router.add_get("/cast/{token}/{name}", self._serve)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, 0)
        await site.start()
        self.port = int(self.runner.addresses[0][1])

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/cast/{self.token}/index.m3u8"

    async def _serve(self, request):
        from aiohttp import web

        if request.match_info["token"] != self.token:
            raise web.HTTPNotFound()
        name = request.match_info["name"]
        self.requests.append((time.perf_counter(), name))
        path = self.folder / name
        if "/" in name or "\\" in name or not path.is_file():
            raise web.HTTPNotFound()
        if name.endswith(".m3u8"):
            text = path.read_text(encoding="utf-8")
            if self.start_offset is not None:
                text = text.replace(
                    "#EXTM3U\n",
                    f"#EXTM3U\n#EXT-X-START:TIME-OFFSET={self.start_offset:.1f}\n", 1)
            return web.Response(text=text, content_type="application/vnd.apple.mpegurl",
                                headers={"Cache-Control": "no-cache"})
        kind = "video/mp2t" if name.endswith(".ts") else "video/mp4"
        return web.Response(body=path.read_bytes(), content_type=kind)

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()


# --- the Apple TV --------------------------------------------------------------------------------

APPLE_TV_MODELS = {"AppleTV4K", "AppleTV4KGen2", "AppleTV4KGen3"}


async def find_tv(storage_path: Path, *, paired: bool = True):
    import pyatv
    from pyatv.storage.file_storage import FileStorage

    loop = asyncio.get_running_loop()
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage = FileStorage(str(storage_path), loop)
    await storage.load()
    found = await pyatv.scan(loop, timeout=5, storage=storage)
    tvs = []
    for conf in found:
        if conf.device_info.model.name not in APPLE_TV_MODELS:
            continue
        airplay = conf.get_service(pyatv.const.Protocol.AirPlay)
        if airplay is not None and (airplay.credentials or not paired):
            tvs.append(conf)
    if len(tvs) != 1:
        raise SystemExit(f"expected one {'paired ' if paired else ''}Apple TV 4K, found {len(tvs)}")
    return tvs[0], storage


async def pair(args: argparse.Namespace) -> dict:
    """AirPlay pairing (the TV shows a PIN; it is read from --pin-file once written)."""
    import pyatv

    conf, storage = await find_tv(Path(args.storage), paired=False)
    pin_file = Path(args.pin_file)
    pin_file.unlink(missing_ok=True)
    pairing = await pyatv.pair(conf, pyatv.const.Protocol.AirPlay, asyncio.get_running_loop(),
                               storage=storage)
    try:
        await pairing.begin()
        print("PIN showing on the TV; waiting for", pin_file.name, flush=True)
        deadline = time.monotonic() + args.pin_wait
        while not pin_file.exists() or not pin_file.read_text().strip():
            if time.monotonic() > deadline:
                raise SystemExit("no PIN arrived")
            await asyncio.sleep(0.5)
        pairing.pin(int(pin_file.read_text().strip()))
        await pairing.finish()
        ok = pairing.has_paired
    finally:
        await pairing.close()
        pin_file.unlink(missing_ok=True)
    if ok:
        await storage.save()
    return {"paired": ok}


class PlaybackLog:
    """Records the TV's playback-info replies (pyatv polls them once a second)."""

    def __init__(self) -> None:
        self.samples: list[tuple[float, dict]] = []

    def install(self) -> None:
        from pyatv.protocols.airplay import player

        original = player.decode_bplist_from_body

        def recording(resp):
            parsed = original(resp)
            self.samples.append((time.perf_counter(), dict(parsed)))
            return parsed

        player.decode_bplist_from_body = recording


class SystemLoad:
    def __init__(self) -> None:
        import psutil

        self.psutil = psutil
        self.proc = psutil.Process()
        self.proc.cpu_percent(None)
        psutil.cpu_percent(None)
        self.cpu: list[float] = []
        self.total: list[float] = []
        self.gpu: list[tuple[int, int]] = []

    def sample(self) -> None:
        self.cpu.append(self.proc.cpu_percent(None))
        self.total.append(self.psutil.cpu_percent(None))
        smi = shutil.which("nvidia-smi")
        if smi:
            try:
                out = subprocess.run(
                    [smi, "--query-gpu=utilization.gpu,utilization.encoder",
                     "--format=csv,noheader,nounits"], capture_output=True, text=True,
                    timeout=5).stdout.strip().splitlines()[0]
                g, e = (int(x) for x in out.split(","))
                self.gpu.append((g, e))
            except Exception:
                pass


def clock_window() -> subprocess.Popen:
    """A large on-screen clock (wall time to the millisecond), to photograph next to the TV."""
    code = (
        "import tkinter as tk, time\n"
        "r=tk.Tk(); r.title('Spike I clock'); r.attributes('-topmost',True)\n"
        "r.geometry('+40+40'); r.configure(bg='black')\n"
        "l=tk.Label(r,font=('Consolas',72,'bold'),fg='white',bg='black'); l.pack(padx=20,pady=20)\n"
        "def t():\n"
        "  n=time.time(); l.config(text=time.strftime('%H:%M:%S',time.localtime(n))+'.%03d'%int(n%1*1000)); r.after(7,t)\n"
        "t(); r.mainloop()\n"
    )
    return subprocess.Popen([sys.executable, "-c", code])


def local_address_towards(address: str) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((address, 7000))
        return str(probe.getsockname()[0])


def media_seconds(samples: list[tuple[float, dict]]) -> list[tuple[float, float, dict]]:
    return [(t, float(info["position"]), info) for t, info in samples if "position" in info]


async def cast(args: argparse.Namespace) -> dict:
    import pyatv

    conf, storage = await find_tv(Path(args.storage))
    host = local_address_towards(str(conf.address))
    folder = Path(tempfile.mkdtemp(prefix="tandem-cast-"))
    clock = clock_window() if args.clock else None
    caster = Caster(args, folder)
    server = Server(folder, host, args.start_offset)
    await server.start()
    load = SystemLoad()
    log = PlaybackLog()
    log.install()
    caster.start()
    # Wait until the playlist has enough segments for the TV to start.
    while not (folder / "index.m3u8").exists() or \
            (folder / "index.m3u8").read_text().count("#EXTINF") < args.wait_segments:
        await asyncio.sleep(0.05)
    ready = caster.media_now()
    loop = asyncio.get_running_loop()
    if args.airplay_version != "auto":
        # tvOS answers 403 to pyatv's AirPlay 2 /play; the AirPlay 1 request plays (Spike I).
        from pyatv.settings import AirPlayVersion

        settings = await storage.get_settings(conf)
        settings.protocols.raop.protocol_version = AirPlayVersion(args.airplay_version)
    atv = await pyatv.connect(conf, loop, storage=storage)
    asked = time.perf_counter()
    play = loop.create_task(atv.stream.play_url(server.url))
    lags: list[tuple[float, float]] = []
    load_due = time.perf_counter()
    first_play = None
    ended_reason = "time"
    try:
        end = time.perf_counter() + args.seconds
        while time.perf_counter() < end:
            await asyncio.sleep(0.5)
            if play.done():
                exc = play.exception()
                ended_reason = f"tv stopped ({type(exc).__name__})" if exc else "tv stopped"
                break
            if time.perf_counter() >= load_due:
                load.sample()
                load_due += 5
            positions = media_seconds(log.samples)
            if positions:
                t, pos, info = positions[-1]
                if info.get("rate", 0) and first_play is None:
                    first_play = t
                if info.get("rate", 0):
                    lags.append((t - caster.t0, (t - caster.t0) - pos))
    finally:
        play.cancel()
        try:
            await atv.stream.stop() if hasattr(atv.stream, "stop") else None
        except Exception:
            pass
        atv.close()
        caster.stop()
        await server.stop()
        if clock is not None:
            clock.terminate()

    infos = [i for _, i in log.samples]
    stalls = sum(1 for a, b in zip(infos, infos[1:]) if a.get("rate", 0) and not b.get("rate", 0))
    lag_values = [lag for _, lag in lags]
    seg_requests = [(t - caster.t0, n) for t, n in server.requests if not n.endswith(".m3u8")]
    keys_seen = sorted({k for i in infos for k in i})
    result = {
        "encoder": caster.encoder,
        "size": args.size, "fps": args.fps, "segment_s": args.segment,
        "list_size": args.list_size, "start_offset": args.start_offset,
        "segment_type": args.segment_type, "seconds": args.seconds, "ended": ended_reason,
        "airplay_version": args.airplay_version,
        "first_segments_ready_s": round(ready, 2),
        "tv_started_after_request_s": round(first_play - asked, 2) if first_play else None,
        "lag_s": {"median": round(statistics.median(lag_values), 2),
                  "p5": round(pct(lag_values, 5), 2), "p95": round(pct(lag_values, 95), 2),
                  "first": round(lag_values[0], 2), "last": round(lag_values[-1], 2)}
        if lag_values else None,
        "stalls": stalls,
        "frames": caster.frames, "late_ticks": caster.late,
        "frame_work_ms": {"median": round(statistics.median(caster.frame_ms), 1),
                          "p95": round(pct(caster.frame_ms, 95), 1)},
        "cpu_process_pct": round(statistics.mean(load.cpu), 1) if load.cpu else None,
        "cpu_total_pct": round(statistics.mean(load.total), 1) if load.total else None,
        "gpu_pct": round(statistics.mean(g for g, _ in load.gpu), 1) if load.gpu else None,
        "nvenc_pct": round(statistics.mean(e for _, e in load.gpu), 1) if load.gpu else None,
        "audio_padded_s": round(caster.audio.padded / 4 / SAMPLE_RATE, 1) if caster.audio else None,
        "audio_dropped_s": round(caster.audio.dropped / 4 / SAMPLE_RATE, 1) if caster.audio else None,
        "playback_info_keys": keys_seen,
        "segment_requests_first10": [(round(t, 2), n) for t, n in seg_requests[:10]],
        "lag_series": [(round(t, 1), round(lag, 2)) for t, lag in lags[::10]],
    }
    shutil.rmtree(folder, ignore_errors=True)
    return result


def local(args: argparse.Namespace) -> dict:
    folder = Path(tempfile.mkdtemp(prefix="tandem-cast-"))
    caster = Caster(args, folder)
    caster.start()
    time.sleep(args.seconds)
    caster.stop()
    playlist = (folder / "index.m3u8").read_text()
    sizes = [p.stat().st_size for p in folder.glob("*.ts")] or [p.stat().st_size for p in folder.glob("*.m4s")]
    shutil.rmtree(folder, ignore_errors=True)
    return {
        "encoder": caster.encoder, "frames": caster.frames, "late_ticks": caster.late,
        "frame_work_ms": {"median": round(statistics.median(caster.frame_ms), 1),
                          "p95": round(pct(caster.frame_ms, 95), 1)},
        "segments_listed": playlist.count("#EXTINF"),
        "segment_kb_median": round(statistics.median(sizes) / 1024) if sizes else None,
        "audio_padded_s": round(caster.audio.padded / 4 / SAMPLE_RATE, 1) if caster.audio else None,
    }


def main() -> int:
    make_dpi_aware()
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["pair", "local", "cast"])
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--encoder", default="auto")
    parser.add_argument("--size", default="1920x1080")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--bitrate", type=int, default=8_000_000)
    parser.add_argument("--segment", type=float, default=1.0)
    parser.add_argument("--list-size", type=int, default=6)
    parser.add_argument("--segment-type", choices=["mpegts", "fmp4"], default="mpegts")
    parser.add_argument("--start-offset", type=float, default=None)
    parser.add_argument("--wait-segments", type=int, default=3)
    parser.add_argument("--source", choices=["desktop", "pattern"], default="desktop")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--clock", action="store_true")
    parser.add_argument("--label", default="run")
    parser.add_argument("--storage", default=str(ROOT / "local" / "spike-i" / "pyatv-storage.json"))
    parser.add_argument("--pin-file", default=str(ROOT / "local" / "spike-i" / "pin.txt"))
    parser.add_argument("--airplay-version", choices=["auto", "1", "2"], default="auto")
    parser.add_argument("--pin-wait", type=float, default=1800,
                        help="seconds to wait for the PIN file (the PIN is relayed by hand)")
    args = parser.parse_args()
    if args.mode == "pair":
        print(json.dumps(asyncio.run(pair(args))))
        return 0
    result = local(args) if args.mode == "local" else asyncio.run(cast(args))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.label}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "lag_series"}, indent=1))
    sys.stdout.flush()
    os._exit(0)  # dxcam crashes in its COM cleanup (Spike E)


if __name__ == "__main__":
    raise SystemExit(main())
