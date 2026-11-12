"""Capture a screen and encode it as a live HLS stream (Cast screen, Spike I).

Desktop duplication through dxcam hands over each frame as BGRA in main memory; PyAV (its
bundled FFmpeg) scales it, encodes H.264 on the GPU where it can (NVENC, then Windows' Media
Foundation, then x264 on the CPU) and writes an HLS playlist of one-second MPEG-TS segments,
with the PC's sound as AAC. One thread does all of it at a steady frame rate.

Only `engine/adapters` imports dxcam and PyAV. Nothing here logs what is on screen.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from contextlib import suppress
from fractions import Fraction
from pathlib import Path
from typing import Any

from tandem.engine.audio import PcmCapture
from tandem.engine.screen_cast import PLAYLIST, CastError, CastSettings, Screen

_LOGGER = logging.getLogger(__name__)

SAMPLE_RATE = 44100
_BYTES_PER_SAMPLE = 4  # 16-bit stereo
_SOUND_HELD = SAMPLE_RATE * _BYTES_PER_SAMPLE // 5
"""At most 200 ms of sound waits for the encoder; older sound is dropped (clock drift)."""

ENCODERS = ("h264_nvenc", "h264_mf", "libx264")
"""Best first. NVENC is fastest (Spike E); Media Foundation ships with Windows and finds the
GPU's encoder itself; x264 runs on the CPU."""

LOW_LATENCY: dict[str, dict[str, str]] = {
    "h264_nvenc": {
        "preset": "p1",
        "tune": "ull",
        "rc": "cbr",
        "zerolatency": "1",
        "delay": "0",
        "rc-lookahead": "0",
        "forced-idr": "1",
    },
    "h264_mf": {"scenario": "display_remoting", "rate_control": "cbr", "hw_encoding": "1"},
    "libx264": {"preset": "ultrafast", "tune": "zerolatency"},
}


def available() -> bool:
    """dxcam and PyAV are installed (they come with the window, the `ui` extra)."""
    try:
        import av  # noqa: F401  # pyright: ignore[reportUnusedImport]
        import dxcam  # noqa: F401  # pyright: ignore[reportUnusedImport, reportMissingTypeStubs]
    except Exception:
        return False
    return True


def screens() -> list[Screen]:  # pragma: no cover - depends on the PC's displays
    """The displays desktop duplication can capture, on any GPU. Sizes only, no names."""
    if not available():
        return []
    import dxcam  # pyright: ignore[reportMissingTypeStubs]

    found: list[Screen] = []
    try:
        outputs: Any = dxcam.output_info()  # pyright: ignore[reportUnknownMemberType]
    except Exception:
        return []
    # One line per output: "Device[d] Output[o]: Res:(w, h) Rot:r Primary:True"
    for line in str(outputs).splitlines():
        try:
            device = int(line.split("Device[", 1)[1].split("]", 1)[0])
            output = int(line.split("Output[", 1)[1].split("]", 1)[0])
            size = line.split("Res:(", 1)[1].split(")", 1)[0]
            width, height = (int(x) for x in size.split(","))
        except (IndexError, ValueError):
            continue
        found.append(Screen(device * 16 + output, width, height, "Primary:True" in line))
    found.sort(key=lambda s: (not s.primary, s.index))
    return found


def pick_encoder(width: int, height: int, fps: int) -> str:  # pragma: no cover - needs codecs
    import av

    for name in ENCODERS:
        try:
            ctx: Any = av.CodecContext.create(name, "w")
            ctx.width, ctx.height = width, height
            ctx.time_base = Fraction(1, fps)
            ctx.pix_fmt = "yuv420p" if name == "libx264" else "nv12"
            ctx.options = dict(LOW_LATENCY.get(name, {}))
            ctx.open()
        except Exception:
            continue
        return name
    raise CastError(CastError.ENCODER)


class _Sound:
    """The PC's sound from a capture, handed out paced to the stream's clock."""

    def __init__(self, capture: PcmCapture) -> None:
        self._capture = capture
        self._chunks: deque[bytes] = deque()
        self._held = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        self._capture.start(self._on_pcm)

    def stop(self) -> None:
        self._capture.stop()

    def _on_pcm(self, data: bytes) -> None:
        with self._lock:
            self._chunks.append(data)
            self._held += len(data)
            while self._held > _SOUND_HELD and self._chunks:
                self._held -= len(self._chunks.popleft())

    def take(self, samples: int) -> bytes:
        """`samples` frames of 16-bit stereo; silence where nothing was captured (Windows
        sends nothing at all while nothing plays)."""
        want = samples * _BYTES_PER_SAMPLE
        out = bytearray()
        with self._lock:
            while len(out) < want and self._chunks:
                chunk = self._chunks.popleft()
                need = want - len(out)
                out += chunk[:need]
                if len(chunk) > need:
                    self._chunks.appendleft(chunk[need:])
                self._held -= min(len(chunk), need)
        out += bytes(want - len(out))
        return bytes(out)


class DxcamScreenEncoder:  # pragma: no cover - needs a display, a GPU and FFmpeg's codecs
    """A `ScreenEncoder`: dxcam capture, PyAV encode, HLS files in a folder."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._failed = False
        self._camera: Any = None
        self._sound: _Sound | None = None

    @property
    def failed(self) -> bool:
        return self._failed

    def start(self, folder: Path, settings: CastSettings, sound: PcmCapture | None) -> None:
        import av
        import dxcam  # pyright: ignore[reportMissingTypeStubs]

        encoder = pick_encoder(settings.width, settings.height, settings.fps)
        device, output = divmod(settings.screen, 16)
        try:
            camera: Any = dxcam.create(  # pyright: ignore[reportUnknownMemberType]
                device_idx=device, output_idx=output, output_color="BGRA"
            )
        except Exception as exc:
            raise CastError(CastError.NO_SCREEN) from exc
        if camera is None:
            raise CastError(CastError.NO_SCREEN)
        flags = ["independent_segments", "delete_segments"]
        container: Any = av.open(
            str(folder / PLAYLIST),
            mode="w",
            format="hls",
            options={
                "hls_time": f"{settings.segment_seconds:g}",
                "hls_list_size": str(settings.list_size),
                "hls_flags": "+".join(flags),
                "hls_segment_type": "mpegts",
            },
        )
        video: Any = container.add_stream(encoder, rate=settings.fps)
        video.width, video.height = settings.width, settings.height
        video.pix_fmt = "yuv420p" if encoder == "libx264" else "nv12"
        video.time_base = Fraction(1, 90000)
        video.bit_rate = settings.bitrate
        context: Any = video.codec_context
        context.gop_size = max(1, round(settings.fps * settings.segment_seconds))
        context.max_b_frames = 0
        options = dict(LOW_LATENCY.get(encoder, {}))
        if encoder == "libx264":
            gop = context.gop_size
            options["x264-params"] = f"keyint={gop}:min-keyint={gop}:scenecut=0"
        context.options = options
        audio: Any = None
        if sound is not None:
            audio = container.add_stream("aac", rate=SAMPLE_RATE)
            audio.layout = "stereo"
            audio.time_base = Fraction(1, SAMPLE_RATE)
            audio.bit_rate = 128_000
            self._sound = _Sound(sound)
            self._sound.start()
        camera.start(target_fps=settings.fps, video_mode=True)
        self._camera = camera
        _LOGGER.info("Casting with %s at %dx%d", encoder, settings.width, settings.height)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(container, video, audio, settings),
            name="screen-cast",
            daemon=True,
        )
        self._thread.start()

    def _run(self, container: Any, video: Any, audio: Any, settings: CastSettings) -> None:
        import av
        import numpy as np

        period = 1 / settings.fps
        started = time.perf_counter()
        next_tick = started
        written = 0  # sound frames written
        try:
            while not self._stop.is_set():
                now = time.perf_counter()
                if now < next_tick:
                    time.sleep(next_tick - now)
                elif now - next_tick > period:
                    next_tick = now  # fell behind: skip ahead rather than catch up
                raw = self._camera.get_latest_frame()
                frame: Any = av.VideoFrame.from_numpy_buffer(  # pyright: ignore[reportUnknownMemberType]
                    np.ascontiguousarray(raw), format="bgra"
                )
                frame = frame.reformat(
                    width=settings.width,
                    height=settings.height,
                    format=video.pix_fmt,
                    interpolation="FAST_BILINEAR",
                )
                frame.pts = round((time.perf_counter() - started) * 90000)
                frame.time_base = video.time_base
                for packet in video.encode(frame):
                    container.mux(packet)
                if audio is not None and self._sound is not None:
                    due = round((time.perf_counter() - started) * SAMPLE_RATE) - written
                    if due > 0:
                        pcm = np.frombuffer(self._sound.take(due), np.int16).reshape(1, -1)
                        sound: Any = av.AudioFrame.from_ndarray(  # pyright: ignore[reportUnknownMemberType]
                            pcm, format="s16", layout="stereo"
                        )
                        sound.sample_rate = SAMPLE_RATE
                        sound.pts = None  # numbered by the encoder: paced by sample count
                        written += due
                        for packet in audio.encode(sound):
                            container.mux(packet)
                next_tick += period
        except Exception as exc:
            _LOGGER.warning("Screen cast encoder stopped (%s)", type(exc).__name__)
            self._failed = True
        finally:
            try:
                for stream in (video, audio):
                    if stream is not None:
                        for packet in stream.encode():
                            container.mux(packet)
            except Exception:
                pass
            container.close()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=5)
        camera, self._camera = self._camera, None
        if camera is not None:
            # dxcam crashes in release() and its COM cleanup (Spike E): only stop it. dxcam
            # keeps one camera per output and hands the same one back next time.
            with suppress(Exception):
                camera.stop()
        sound, self._sound = self._sound, None
        if sound is not None:
            sound.stop()
