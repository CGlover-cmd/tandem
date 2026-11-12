"""Start Tandem: the engine-side server, the window and the tray icon (ADR-0010).

Threads: pywebview's window must own the main thread on Windows, so the asyncio loop (the
backend, `AppController` and `UiServer`) runs on a second thread and pystray on a third.

This is the composition root: it reaches the real engine only through `tandem.bridge`, so the
rest of `tandem.ui` never imports engine code.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
import threading
from collections.abc import Sequence
from typing import Any

from tandem.ui.app_icons import AiohttpHttp, AppIconStore
from tandem.ui.backend import Backend
from tandem.ui.background_photo import BackgroundPhoto
from tandem.ui.controller import AppController
from tandem.ui.file_picker import WindowFilePicker
from tandem.ui.platform import (
    GlobalHotkey,
    on_quit_request,
    reduce_motion,
    reveal_in_explorer,
    show_start_error,
    store_country,
    ui_data_dir,
)
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


def build(
    args: argparse.Namespace, picker: WindowFilePicker | None = None
) -> tuple[AppController, UiServer]:
    backend: Backend
    icons: AppIconStore | None = None
    if args.demo:  # the real engine on invented devices; invented apps: nothing to look up
        from tandem.bridge import DemoBackend

        backend = DemoBackend(settings_file=ui_data_dir() / "demo-settings.json")
    else:  # pragma: no cover - needs the network
        from tandem.bridge import create_engine_backend

        backend = create_engine_backend()
        icons = AppIconStore(ui_data_dir() / "app-icons", AiohttpHttp(), country=store_country())
    http = None if args.demo else AiohttpHttp()  # the demo never goes online
    photo = BackgroundPhoto(ui_data_dir() / ("demo-photo" if args.demo else "photo"))
    controller = AppController(
        backend,
        demo_mode=args.demo,
        reduce_motion=reduce_motion(),
        icons=icons,
        picker=picker,
        folder_picker=picker,
        photo=photo,
        get_json=None if http is None else http.get_json,
        reveal=reveal_in_explorer,
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
    quit_requested = asyncio.Event()
    loop = asyncio.get_running_loop()

    def stop_soon() -> None:  # setup is about to replace Tandem's files
        with contextlib.suppress(RuntimeError):  # the loop already closed
            loop.call_soon_threadsafe(quit_requested.set)

    on_quit_request(stop_soon)
    try:
        await quit_requested.wait()
    finally:
        await server.stop()
        await controller.stop()
    return 0


def _run_with_window(args: argparse.Namespace) -> int:  # pragma: no cover - checked by hand
    import webview  # pyright: ignore[reportMissingTypeStubs]

    from tandem.ui.icon import write_ico
    from tandem.ui.platform import claim_single_instance
    from tandem.ui.tray import Tray

    if not args.demo and not claim_single_instance():
        _LOGGER.info("Tandem is already running; this copy exits")
        return 0
    wv: Any = webview
    loop = asyncio.new_event_loop()
    picker = WindowFilePicker()
    controller, server = build(args, picker)
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
    picker.attach(window)

    def show_window() -> None:
        window.show()
        window.restore()
        loop.call_soon_threadsafe(controller.set_window_visible, True)

    def quit_app() -> None:
        quitting.set()
        window.destroy()

    tray = Tray(controller, loop, show_window=show_window, quit_app=quit_app)

    def quit_for_setup() -> None:  # the installer or uninstaller is about to change our files
        window.events.shown.wait()  # destroy() needs the window up
        quit_app()

    on_quit_request(quit_for_setup)

    def on_closing() -> bool:
        # Closing the window keeps Tandem running in the tray; Quit in the tray ends it.
        if quitting.is_set():
            return True
        threading.Thread(target=window.hide, daemon=True).start()
        loop.call_soon_threadsafe(controller.set_window_visible, False)
        tray.told_hidden()
        return False

    window.events.closing += on_closing
    window.events.minimized += lambda: loop.call_soon_threadsafe(
        controller.set_window_visible, False
    )
    window.events.restored += lambda: loop.call_soon_threadsafe(controller.set_window_visible, True)

    def on_hotkey() -> None:  # Ctrl+Alt+K from anywhere: bring Tandem up with Commands open
        show_window()
        loop.call_soon_threadsafe(controller.request_commands)

    hotkey = GlobalHotkey(on_hotkey)
    hotkey.start()
    tray.start()
    icon = write_ico(ui_data_dir() / "tandem.ico")
    code = 0
    try:
        wv.start(icon=str(icon), private_mode=True)
    except Exception as error:
        # Without this, the tray's thread kept a windowless Tandem running, holding the
        # single-instance lock, so every later launch quietly quit too (1.2.0).
        _LOGGER.error("Tandem couldn't open its window: %s", type(error).__name__)
        show_start_error()
        code = 1
    finally:
        tray.stop()
        hotkey.stop()
        loop.call_soon_threadsafe(loop.stop)
        stopped.wait(timeout=5)
    return code
