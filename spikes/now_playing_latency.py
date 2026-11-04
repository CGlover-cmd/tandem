"""Music: how fast does Tandem's now-playing bar follow a track change? (Phase 6 exit test)

Runs the app's real path in this process (engine, bridge, controller and the loopback
WebSocket the window uses) and listens to Windows' media controls directly as well. For every
track change it prints the delay from Windows reporting it to the window's state showing it.

`--page` also serves a small loopback page of quiet generated test tones that changes "track"
every 12 seconds; it prints the page's address to open in a browser (keep the tab visible:
browsers hold back media in hidden tabs). Without it, play something in any app (e.g. the
Apple Music app) and change tracks yourself. Timings are only as fine as Windows' monotonic
clock (about 16 ms), so "0 ms" means under that.

Privacy: prints app names, delays and yes/no flags only, never titles or artists, and nothing
about devices on the network.

Usage (from the repo root, with the dev virtualenv's python.exe):
    python spikes/now_playing_latency.py --page [--seconds 60] [--debug]
    python spikes/now_playing_latency.py --seconds 120
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import math
import struct
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

TONES = (440.0, 554.4, 659.3)  # A4, C#5, E5
TRACKS = [f"/tone/{n}.wav" for n in range(1, len(TONES) + 1)]
PAGE = """<!doctype html><meta charset="utf-8"><title>Tandem test audio</title>
<p>Tandem now-playing test: quiet test tones, changing every 12 s.</p>
<audio id="a" autoplay></audio>
<script>
const tracks = TRACKS;
const audio = document.getElementById("a");
audio.volume = 0.05;
let n = 0;
function play() {
  audio.src = tracks[n % tracks.length];
  navigator.mediaSession.metadata = new MediaMetadata({
    title: "Test tone " + (n % tracks.length + 1), artist: "Tandem test" });
  audio.play().catch(() => {});
  n++;
}
play();
setInterval(play, 12000);
</script>
"""


class RawEvents:
    """Windows' media events, time-stamped on the WinRT thread that raises them."""

    def __init__(self) -> None:
        self.times: list[float] = []
        self._lock = threading.Lock()
        self._manager: Any = None
        self._session: Any = None
        self._tokens: list[tuple[Any, Any]] = []

    def _mark(self, *_args: Any) -> None:
        with self._lock:
            self.times.append(time.monotonic())

    def _follow(self, *_args: Any) -> None:
        self._mark()
        for remove, token in self._tokens:
            try:
                remove(token)
            except OSError:
                pass
        self._session = session = self._manager.get_current_session()
        self._tokens = (
            []
            if session is None
            else [
                (
                    session.remove_media_properties_changed,
                    session.add_media_properties_changed(self._mark),
                ),
                (
                    session.remove_playback_info_changed,
                    session.add_playback_info_changed(self._mark),
                ),
            ]
        )

    async def start(self) -> None:
        from winrt.windows.media.control import (  # pyright: ignore[reportMissingModuleSource]
            GlobalSystemMediaTransportControlsSessionManager as Manager,
        )

        self._manager = await Manager.request_async()
        self._manager.add_current_session_changed(self._follow)
        self._manager.add_sessions_changed(self._follow)
        self._follow()

    def burst_start(self, since: float, until: float, gap: float = 1.5) -> float | None:
        """When the last burst of Windows events before `until` began (events less than
        `gap` seconds apart count as one burst, e.g. a browser dropping and re-making its
        session on a track change)."""
        with self._lock:
            found = sorted(t for t in self.times if since < t <= until)
        if not found:
            return None
        start = found[-1]
        for t in reversed(found[:-1]):
            if start - t > gap:
                break
            start = t
        return start


def _fingerprint(music: dict[str, Any] | None) -> str | None:
    """Tell tracks apart without keeping their titles."""
    if music is None:
        return None
    text = json.dumps([music.get("app"), music.get("title"), music.get("artist")])
    return hashlib.sha256(text.encode()).hexdigest()


def tone(frequency: float, seconds: float = 20.0, rate: int = 22_050) -> bytes:
    """A quiet sine tone as a WAV file."""
    frames = b"".join(
        struct.pack("<h", int(3000 * math.sin(2 * math.pi * frequency * i / rate)))
        for i in range(int(seconds * rate))
    )
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(frames)
    return out.getvalue()


async def serve_page() -> tuple[web.AppRunner, str]:
    page = PAGE.replace("TRACKS", json.dumps(TRACKS))
    tones = {f"{n}.wav": tone(f) for n, f in enumerate(TONES, start=1)}

    async def index(_request: web.Request) -> web.Response:
        return web.Response(text=page, content_type="text/html")

    async def wav(request: web.Request) -> web.Response:
        data = tones.get(request.match_info["name"])
        if data is None:
            raise web.HTTPNotFound()
        return web.Response(body=data, content_type="audio/wav")

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/tone/{name}", wav)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = int(runner.addresses[0][1])
    return runner, f"http://127.0.0.1:{port}/"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", action="store_true", help="serve the test-tone page")
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--debug", action="store_true", help="print event times too")
    args = parser.parse_args()

    from tandem.bridge import create_engine_backend
    from tandem.ui.controller import AppController
    from tandem.ui.server import UiServer

    raw = RawEvents()
    await raw.start()
    controller = AppController(create_engine_backend())
    server = UiServer(controller, static_dir=Path(tempfile.mkdtemp()))
    await server.start()
    controller.runner.run(controller.start())

    page_runner: web.AppRunner | None = None
    if args.page:
        page_runner, url = await serve_page()
        print(f"Open {url} in a browser and leave the tab in view.", flush=True)

    delays: list[float] = []
    apps: set[str] = set()
    last: str | None = None
    last_change = time.monotonic()
    ws_url = f"ws://127.0.0.1:{server.port}/ws?token={server.token}"
    start = time.monotonic()
    deadline = start + args.seconds
    print(f"Watching for {args.seconds:.0f} s...", flush=True)
    try:
        async with (
            aiohttp.ClientSession() as http,
            http.ws_connect(ws_url, headers={"Origin": server.origin}) as socket,
        ):
            while (remaining := deadline - time.monotonic()) > 0:
                try:
                    message = await asyncio.wait_for(socket.receive_str(), remaining)
                except TimeoutError:
                    break
                now = time.monotonic()
                music = json.loads(message)["state"]["music"]
                fingerprint = _fingerprint(music)
                if fingerprint == last:
                    continue
                reported = raw.burst_start(last_change, now)
                if args.debug:
                    with raw._lock:  # pyright: ignore[reportPrivateUsage]
                        times = [f"{t - start:.2f}" for t in raw.times if t > last_change]
                    print(f"  update at {now - start:.2f}s; Windows events since: {times}")
                delay = None if reported is None else (now - reported) * 1000
                app = None if music is None else music.get("app")
                if app:
                    apps.add(app)
                artwork = music is not None and music.get("artwork") is not None
                timing = "no Windows event seen" if delay is None else f"{delay:6.0f} ms"
                print(
                    f"change: {timing}  app={app or '-'}  has title="
                    f"{'yes' if music and music.get('title') else 'no'}  artwork="
                    f"{'yes' if artwork else 'no'}",
                    flush=True,
                )
                if delay is not None and last is not None:
                    delays.append(delay)
                last, last_change = fingerprint, now
    finally:
        if page_runner is not None:
            await page_runner.cleanup()
        await server.stop()
        await controller.stop()
    if delays:
        print(
            f"Track changes: {len(delays)}; delay max {max(delays):.0f} ms, "
            f"mean {sum(delays) / len(delays):.0f} ms; apps: {', '.join(sorted(apps))}"
        )
    else:
        print("No track changes seen.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
