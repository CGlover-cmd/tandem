"""Start Tandem: the engine-side server, the window and the tray icon (ADR-0010).

Threads: pywebview's window must own the main thread on Windows, so the asyncio loop (the
backend, `AppController` and `UiServer`) runs on a second thread and pystray on a third.

This is the composition root: it reaches the real engine only through `tandem.bridge`, so the
rest of `tandem.ui` never imports engine code.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
from collections.abc import Sequence
from typing import Any

from tandem.ui.app_icons import AiohttpHttp, AppIconStore
from tandem.ui.backend import Backend
from tandem.ui.controller import AppController
from tandem.ui.demo_backend import DemoBackend
from tandem.ui.platform import reduce_motion, store_country, ui_data_dir
from tandem.ui.server import UiServer

_LOGGER = logging.getLogger(__name__)

WINDOW_SIZE = (980, 660)
MIN_SIZE = (560, 440)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tandem-ui", description="Tandem's window.")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="show invented devices instead of the ones on your network",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="only run the local server and print the page address (for development)",
    )
    parser.add_argument(
        "--port", type=int, default=0, help="local port for the server (default: any free one)"
    )
    parser.add_argument(
        "--dev-origin",
        action="append",
        default=[],
        metavar="ORIGIN",
        help="also accept the page from this origin, e.g. the Vite dev server",
    )
    return parser.parse_args(argv)


def build(args: argparse.Namespace) -> tuple[AppController, UiServer]:
    backend: Backend
    icons: AppIconStore | None = None
    if args.demo:  # invented apps: nothing to look up
        backend = DemoBackend(appearance_file=ui_data_dir() / "demo-appearance.json")
    else:  # pragma: no cover - needs the network
        from tandem.bridge import create_engine_backend

        backend = create_engine_backend()
        icons = AppIconStore(ui_data_dir() / "app-icons", AiohttpHttp(), country=store_country())
    controller = AppController(
        backend, demo_mode=args.demo, reduce_motion=reduce_motion(), icons=icons
    )
    server = UiServer(
        controller,
        port=args.port,
        extra_origins=args.dev_origin,
        icon_dir=icons.folder if icons is not None else None,
    )
    return controller, server


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.demo:  # the real engine sets up its own redacted logging
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.no_window:
        return asyncio.run(_serve_only(args))
    return _run_with_window(args)  # pragma: no cover - needs a desktop; checked by hand


async def _serve_only(args: argparse.Namespace) -> int:
    controller, server = build(args)
    await server.start()
    controller.runner.run(controller.start())
    # Printed, not logged: the address carries this launch's token.
    print(f"Tandem is running. Open {server.url}", flush=True)
    for origin in args.dev_origin:
        print(f"  or, from the dev server: {origin}/?token={server.token}", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()
        await controller.stop()
    return 0


def _run_with_window(args: argparse.Namespace) -> int:  # pragma: no cover - checked by hand
    import webview  # pyright: ignore[reportMissingTypeStubs]

    from tandem.ui.icon import write_ico
    from tandem.ui.tray import Tray

    wv: Any = webview
    loop = asyncio.new_event_loop()
    controller, server = build(args)
    ready = threading.Event()
    stopped = threading.Event()
    failed: list[BaseException] = []

    async def boot() -> None:
        await server.start()
        controller.runner.run(controller.start())

    def run_loop() -> None:
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(boot())
        except Exception as error:
            failed.append(error)
            ready.set()
            stopped.set()
            return
        ready.set()
        loop.run_forever()
        loop.run_until_complete(server.stop())
        loop.run_until_complete(controller.stop())
        loop.close()
        stopped.set()

    threading.Thread(target=run_loop, name="tandem-engine", daemon=True).start()
    ready.wait()
    if failed:
        _LOGGER.error("Tandem couldn't start its local server: %s", type(failed[0]).__name__)
        return 1

    quitting = threading.Event()
    window: Any = wv.create_window(
        "Tandem",
        server.url,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=MIN_SIZE,
        background_color="#F5F5F7",
    )

    def show_window() -> None:
        window.show()
        window.restore()

    def quit_app() -> None:
        quitting.set()
        window.destroy()

    tray = Tray(controller, loop, show_window=show_window, quit_app=quit_app)

    def on_closing() -> bool:
        # Closing the window keeps Tandem running in the tray; Quit in the tray ends it.
        if quitting.is_set():
            return True
        threading.Thread(target=window.hide, daemon=True).start()
        tray.told_hidden()
        return False

    window.events.closing += on_closing
    tray.start()
    icon = write_ico(ui_data_dir() / "tandem.ico")
    wv.start(icon=str(icon), private_mode=True)

    tray.stop()
    loop.call_soon_threadsafe(loop.stop)
    stopped.wait(timeout=5)
    return 0
