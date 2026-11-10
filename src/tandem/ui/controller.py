"""UI state and logic, in plain Python (ADR-0010).

The web front end only renders `AppController.snapshot()` and sends commands back, so
everything that needs testing (sorting, the pairing state machine, which action a card
offers) lives here and runs under pytest without a window.

Messages for the user are sent as codes (`{"code": "wrongPin"}`); the front end holds the
words, so translations live in one place. A `BackendError` carries a `Problem` code too,
which goes to the window as it is.

Now-playing titles and typed commands are personal: they go to the window only, never to a
log.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import platform
import re
import time
import urllib.parse
import webbrowser
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Protocol

from tandem import __version__
from tandem.ui.audio_panel import AudioPanel, FilePicker
from tandem.ui.backend import (
    MAX_TEXT,
    PHOTO_BACKGROUND,
    AppearanceChanged,
    AppInfo,
    AudioChanged,
    Backend,
    BackendError,
    BackendEvent,
    CommandOutcome,
    ControlsChanged,
    ControlsSnapshot,
    DeviceKind,
    DeviceRemoved,
    DeviceSnapshot,
    DeviceUpdated,
    DiscoveryChanged,
    HomeUpdated,
    KeyAction,
    LinkState,
    MediaCommand,
    MusicArtwork,
    MusicChanged,
    MusicCommand,
    MusicSnapshot,
    NetworkChanged,
    NetworkSnapshot,
    OutputKind,
    OutputState,
    PairingError,
    PairingFlow,
    RemoteKey,
    SendChanged,
    Theme,
    WrongPinError,
)
from tandem.ui.background_photo import BackgroundPhoto
from tandem.ui.updates import GetJson, Update
from tandem.ui.updates import check as check_for_update
from tandem.ui.window_commands import CommandTable, Fields

_LOGGER = logging.getLogger(__name__)

_PIN = re.compile(r"\d{4}")

MAX_COMMAND = 200
"""Longest typed command the window may send; longer text is ignored."""

Problem = dict[str, str]
Listener = Callable[[], None]


class IconSource(Protocol):
    """Icons for the app launcher (`tandem.ui.app_icons.AppIconStore`)."""

    async def icons(self, app_ids: list[str]) -> dict[str, str]:
        """App ids in, icon URLs on Tandem's own server out, for the apps that have one."""
        ...

    async def close(self) -> None: ...


class TaskRunner:
    """Run coroutines on the asyncio loop, keep them alive, report failures."""

    def __init__(self, on_error: Callable[[BaseException], None]) -> None:
        self._on_error = on_error
        self._tasks: set[asyncio.Task[None]] = set()

    def run(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._done)
        return task

    def _done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self._on_error(error)

    async def drain(self) -> None:
        """Wait for every running task (used by tests and at shutdown)."""
        while self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


class PairingController:
    """The PIN pairing sheet.

    States: closed → starting → enterPin ⇄ checking → done; any → failed; cancel → closed.
    A device that asks for several PINs goes checking → enterPin with `step` one higher.
    """

    def __init__(
        self,
        backend: Backend,
        runner: TaskRunner,
        *,
        on_change: Listener,
        on_paired: Callable[[str], None],
    ) -> None:
        self._backend = backend
        self._runner = runner
        self._on_change = on_change
        self._on_paired = on_paired
        self.state = "closed"
        self.device_id = ""
        self.device_name = ""
        self.error: Problem | None = None
        self.step = 1
        self.steps = 1
        self._flow: PairingFlow | None = None
        self._attempt = 0  # ignores results from an attempt the user has cancelled

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "deviceId": self.device_id,
            "deviceName": self.device_name,
            "error": self.error,
            "step": self.step,
            "steps": self.steps,
        }

    def open(self, device_id: str, device_name: str) -> None:
        if self.state != "closed":
            return
        self._attempt += 1
        self.device_id = device_id
        self.device_name = device_name
        self.error = None
        self.step = 1
        self.steps = 1
        self._set_state("starting")
        self._runner.run(self._begin(self._attempt))

    def submit_pin(self, pin: str) -> None:
        if self.state != "enterPin" or self._flow is None:
            return
        pin = pin.strip()
        if not _PIN.fullmatch(pin):
            self.error = {"code": "pinFormat"}
            self._on_change()
            return
        self.error = None
        self._set_state("checking")
        self._runner.run(self._submit(self._attempt, self._flow, pin))

    def cancel(self) -> None:
        flow = self._flow
        if flow is not None and self.state in ("enterPin", "checking"):
            self._runner.run(flow.cancel())
        self.close()

    def close(self) -> None:
        self._attempt += 1
        self._flow = None
        self.error = None
        self._set_state("closed", force=True)

    async def _begin(self, attempt: int) -> None:
        try:
            flow = await self._backend.begin_pairing(self.device_id)
        except PairingError as error:
            if attempt == self._attempt:
                self._fail(error.code)
            return
        if attempt != self._attempt:
            await flow.cancel()
            return
        self._flow = flow
        self.steps = max(1, flow.steps)
        self._set_state("enterPin")

    async def _submit(self, attempt: int, flow: PairingFlow, pin: str) -> None:
        try:
            more = await flow.submit_pin(pin)
        except WrongPinError:
            if attempt == self._attempt:
                self.error = {"code": "wrongPin"}
                self._set_state("enterPin", force=True)
            return
        except PairingError as error:
            if attempt == self._attempt:
                self._fail(error.code)
            return
        if attempt != self._attempt:
            return
        if more:
            self.step += 1
            self.steps = max(self.steps, self.step)
            self._set_state("enterPin", force=True)
            return
        self._flow = None
        self._set_state("done")
        self._on_paired(self.device_id)

    def _fail(self, code: str) -> None:
        self._flow = None
        self.error = {"code": code or "pairingFailed"}
        self._set_state("failed", force=True)

    def _set_state(self, state: str, *, force: bool = False) -> None:
        if force or state != self.state:
            self.state = state
            self._on_change()


class AppList:
    """A device's apps, as the launcher shows them: loading, ready or failed."""

    def __init__(
        self, items: list[AppInfo] | None = None, icons: dict[str, str] | None = None
    ) -> None:
        self.state = "loading"
        self.items: list[AppInfo] = items or []
        self.icons: dict[str, str] = icons or {}
        self.error: Problem | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "items": [
                {"id": app.id, "name": app.name, "icon": self.icons.get(app.id)}
                for app in self.items
            ],
            "error": self.error,
        }


class CommandBar:
    """The typed command bar (Phase 10a).

    The front end keeps the text box itself and sends each edit: `preview` says what Enter
    would do, and `run` does it. Each preview and result carries the text it is for, so the
    page can ignore one that arrives after the user has typed on.
    """

    def __init__(self, backend: Backend, runner: TaskRunner, *, on_change: Listener) -> None:
        self._backend = backend
        self._runner = runner
        self._on_change = on_change
        self.text = ""
        self.preview_outcome: CommandOutcome | None = None
        self.running = False
        self.result: CommandOutcome | None = None
        self.result_for = ""
        self._attempt = 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "preview": _outcome_json(self.preview_outcome),
            "running": self.running,
            "result": _outcome_json(self.result),
            "resultFor": self.result_for,
        }

    def preview(self, text: str) -> None:
        if len(text) > MAX_COMMAND:
            return
        self.text = text
        self.preview_outcome = self._backend.preview_command(text)
        self._on_change()

    def run(self, text: str) -> None:
        if len(text) > MAX_COMMAND or not text.strip():
            return
        self._attempt += 1
        self.text = text
        self.running = True
        self._on_change()
        self._runner.run(self._run(self._attempt, text))

    def clear(self) -> None:
        """Forget the text and any result (the bar was closed)."""
        self._attempt += 1
        self.text = ""
        self.preview_outcome = None
        self.running = False
        self.result = None
        self.result_for = ""
        self._on_change()

    async def _run(self, attempt: int, text: str) -> None:
        try:
            outcome = await self._backend.run_command(text)
        except BackendError as error:
            outcome = CommandOutcome("failed", "problem", {"problem": error.code})
        finally:
            if attempt == self._attempt:
                self.running = False
        if attempt != self._attempt:
            return
        self.result = outcome
        self.result_for = text
        self._on_change()


ISSUES_URL = "https://github.com/CGlover-cmd/tandem/issues/new"


def issue_url(version: str = __version__, windows: str | None = None) -> str:
    """A new GitHub issue with the facts that help and nothing personal."""
    windows = platform.version() if windows is None else windows
    body = (
        f"Tandem {version} on Windows {windows}\n\n"
        "**What happened:**\n\n\n"
        "**What I expected:**\n\n\n"
        "Tandem just saved a diagnostics zip and showed it in File Explorer. Names, addresses "
        "and identifiers in it are replaced, but have a look first, then drag it here."
    )
    query = urllib.parse.urlencode({"title": "Problem: ", "body": body})
    return f"{ISSUES_URL}?{query}"


_APPEARANCE_FLAGS = {
    "appIcons": "app_icons",
    "onboarded": "onboarded",
    "updateCheck": "update_check",
    "restoreOutputs": "restore_outputs",
    "mutePc": "mute_pc",
}
"""The window's names for the on/off appearance and Advanced settings."""


MAX_ADDRESS = 64
MAX_PASSWORD = 128


def _network_json(network: NetworkSnapshot) -> dict[str, Any]:
    return {
        "addresses": list(network.addresses),
        "adding": network.adding,
        "checking": network.checking,
        "findings": None
        if network.findings is None
        else [finding.value for finding in network.findings],
        "speakersSeen": network.speakers_seen,
    }


class AppController:
    """Everything the window and the tray menu show, and the commands they send."""

    def __init__(
        self,
        backend: Backend,
        *,
        demo_mode: bool = False,
        reduce_motion: bool = False,
        icons: IconSource | None = None,
        picker: FilePicker | None = None,
        photo: BackgroundPhoto | None = None,
        get_json: GetJson | None = None,
        open_url: Callable[[str], object] = webbrowser.open,
        reveal: Callable[[Path], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._backend = backend
        self._icons = icons
        self.photo = photo
        self._get_json = get_json
        """Fetches GitHub's releases list for the update check; None turns it off."""
        self._open_url = open_url
        self._reveal = reveal
        self.update: Update | None = None
        """A newer Tandem on GitHub, if the update check found one."""
        self.reporting = False
        """A diagnostics zip is being written for "Report a problem"."""
        self.commands_requested = 0
        """Bumped by the global hotkey: the window opens its command bar when it changes."""
        """The user's background photo, if this window offers one."""
        self._clock = clock
        self.music: MusicSnapshot | None = None
        self.demo_mode = demo_mode
        self.reduce_motion = reduce_motion
        self.discovering = False
        self.message: Problem | None = None
        self.appearance = backend.appearance()
        self.runner = TaskRunner(self._on_task_error)
        self._devices: dict[str, DeviceSnapshot] = {}
        self._controls: dict[str, ControlsSnapshot] = {}
        self._apps: dict[str, AppList] = {}
        self._text_pending: dict[str, str] = {}
        self._text_sending: set[str] = set()
        self._listeners: list[Listener] = []
        self._after_pairing: dict[str, str] = {}
        """What to do once a device is paired: "audio" turns its sound on (the card's Audio
        button on an unpaired device); anything else just connects."""
        self.pairing = PairingController(
            backend, self.runner, on_change=self._changed, on_paired=self._paired
        )
        self.commands = CommandBar(backend, self.runner, on_change=self._changed)
        self.audio = AudioPanel(backend, self.runner.run, on_change=self._changed, picker=picker)
        self.home = backend.home()
        self.network: NetworkSnapshot = backend.network()
        """Speakers added by address and the network check ("Can't find a speaker?")."""
        self._unsubscribe: Callable[[], None] | None = None
        self._table = self._commands_table()

    # Observing

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Call `listener` (on the asyncio loop thread) after every change."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def devices(self) -> list[DeviceSnapshot]:
        """Devices sorted by name, then id."""
        return sorted(self._devices.values(), key=lambda d: (d.name.casefold(), d.id))

    def device(self, device_id: str) -> DeviceSnapshot | None:
        return self._devices.get(device_id)

    def snapshot(self) -> dict[str, Any]:
        """The whole UI state, ready for JSON."""
        return {
            "devices": [
                _device_json(d, self._controls.get(d.id), self._apps.get(d.id))
                | {"send": self.audio.send_json(d.id), "audio": self.device_audio(d.id)}
                for d in self.devices()
            ],
            "audio": self.audio.snapshot(),
            "home": {
                "enabled": self.home.enabled,
                "running": self.home.running,
                "paired": self.home.paired,
                "setupCode": self.home.setup_code,
                "failed": self.home.failed,
                "switches": [
                    {"id": sid, "name": name, "on": on} for sid, name, on in self.home.switches
                ],
            },
            "discovering": self.discovering,
            "pairing": self.pairing.snapshot(),
            "commands": self.commands.snapshot(),
            "message": self.message,
            "appearance": {
                "theme": self.appearance.theme.value,
                "background": self.appearance.background,
                "appIcons": self.appearance.app_icons,
                "onboarded": self.appearance.onboarded,
                "updateCheck": self.appearance.update_check,
                "restoreOutputs": self.appearance.restore_outputs,
                "mutePc": self.appearance.mute_pc,
                "photoBlur": self.appearance.photo_blur,
                "photo": None if self.photo is None else self.photo.version,
            },
            "network": _network_json(self.network),
            "update": None
            if self.update is None
            else {"version": self.update.version, "url": self.update.url},
            "reporting": self.reporting,
            "commandsRequested": self.commands_requested,
            "demo": self.demo_mode,
            "reduceMotion": self.reduce_motion,
            "music": _music_json(self.music, self._clock()),
        }

    # Lifecycle

    async def start(self) -> None:
        self._unsubscribe = self._backend.subscribe(self._on_event)
        self.music = self._backend.music()
        for device in self._backend.devices():
            self._devices[device.id] = device
            controls = self._backend.controls(device.id)
            if controls is not None:
                self._controls[device.id] = controls
        self.audio.audio = self._backend.audio()
        self.home = self._backend.home()
        self.network = self._backend.network()
        self._changed()
        if self._get_json is not None and self.appearance.update_check:
            self.runner.run(self._check_for_update(self._get_json))
        await self._backend.start()

    async def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self.pairing.close()
        await self.runner.drain()
        if self._icons is not None:
            await self._icons.close()
        await self._backend.stop()

    # Commands

    def activate(self, device_id: str) -> None:
        """The card's main action: pair, connect, disconnect, or cancel a retry."""
        device = self._devices.get(device_id)
        if device is None:
            return
        if device.needs_pairing:
            self.pair(device_id)
        elif device.state in (LinkState.DISCONNECTED, LinkState.FAILED):
            self.connect(device_id)
        elif device.state in (LinkState.CONNECTED, LinkState.WAITING):
            self.disconnect(device_id)
        # CONNECTING: wait for the attempt to finish.

    def connect(self, device_id: str) -> None:
        self.runner.run(self._backend.connect(device_id))

    def device_audio(self, device_id: str) -> str | None:
        """The card's Audio button: "off", "starting", "on" or "failed" for a device that can
        play the PC's sound, None for one that can't."""
        for output in self.audio.audio.outputs:
            if output.id == device_id and output.kind is OutputKind.AIRPLAY:
                return _AUDIO_BUTTON[output.state]
        return None

    def set_device_audio(self, device_id: str, on: bool) -> None:
        """The card's Audio button: play the PC's sound on this device, or stop. An unpaired
        device is paired first, then turned on."""
        device = self._devices.get(device_id)
        if device is None or self.device_audio(device_id) is None:
            return
        if device.needs_pairing:
            if on:
                self._after_pairing[device_id] = "audio"
                self.pair(device_id)
            return
        self.runner.run(self._backend.set_output(device_id, on))

    def open_device(self, device_id: str) -> None:
        """The card's Video and Remote buttons: get the device ready (pair, or connect) while
        the window opens its sheet."""
        device = self._devices.get(device_id)
        if device is None:
            return
        if device.needs_pairing:
            self._after_pairing.pop(device_id, None)
            self.pair(device_id)
        elif device.state in (LinkState.DISCONNECTED, LinkState.FAILED):
            self.connect(device_id)

    def _pair_command(self, device_id: str) -> None:
        self._after_pairing.pop(device_id, None)  # a plain Pair just connects afterwards
        self.pair(device_id)

    def _paired(self, device_id: str) -> None:
        if self._after_pairing.pop(device_id, None) == "audio":
            self.runner.run(self._backend.set_output(device_id, True))  # connects first
        else:
            self.connect(device_id)

    def disconnect(self, device_id: str) -> None:
        self.runner.run(self._backend.disconnect(device_id))

    def pair(self, device_id: str) -> None:
        device = self._devices.get(device_id)
        if device is not None:
            self.pairing.open(device.id, device.name)

    def dismiss_message(self) -> None:
        if self.message is not None:
            self.message = None
            self._changed()

    def press(self, device_id: str, key: RemoteKey, action: KeyAction = KeyAction.TAP) -> None:
        self.runner.run(self._backend.press(device_id, key, action))

    def media(self, device_id: str, command: MediaCommand) -> None:
        self.runner.run(self._backend.media(device_id, command))

    def set_volume(self, device_id: str, level: float) -> None:
        self.runner.run(self._backend.set_volume(device_id, level))

    def music_command(self, command: MusicCommand) -> None:
        """Play/pause, next or previous in the app that's playing on the PC."""
        self.runner.run(self._backend.music_command(command))

    def music_seek(self, position: float) -> None:
        self.runner.run(self._backend.music_seek(position))

    def save_photo(self, data: bytes) -> bool:
        """Use `data` (a JPEG the window made) as the background. False if it was refused."""
        if self.photo is None or not self.photo.save(data):
            return False
        self.set_appearance(background=PHOTO_BACKGROUND)
        self._changed()  # the photo's version changed even if the choice didn't
        return True

    def report_problem(self) -> None:
        """Write a redacted diagnostics zip, show it in Explorer, and open a new GitHub issue
        for the user to describe the problem and attach the zip. Nothing is sent by Tandem."""
        if not self.reporting:
            self.reporting = True
            self._changed()
            self.runner.run(self._report_problem())

    async def _report_problem(self) -> None:
        try:
            bundle = await self._backend.write_diagnostics()
        finally:
            self.reporting = False
            self._changed()
        if bundle is not None and self._reveal is not None:
            self._reveal(bundle)
        self._open_url(issue_url())

    def set_window_visible(self, visible: bool) -> None:
        """Called from the window thread's owner when the window is shown or hidden."""
        self.runner.run(self._backend.set_window_visible(visible))

    def request_commands(self) -> None:
        """The global hotkey: the window (brought to the front by the caller) opens Commands."""
        self.commands_requested += 1
        self._changed()

    async def _check_for_update(self, get_json: GetJson) -> None:
        update = await check_for_update(get_json, __version__)
        if update != self.update:
            self.update = update
            self._changed()

    def music_artwork(self) -> MusicArtwork | None:
        """The artwork for what's playing, for the window only."""
        return self._backend.music_artwork() if self.music is not None else None

    def set_power(self, device_id: str, on: bool) -> None:
        self.runner.run(self._backend.set_power(device_id, on))

    def load_apps(self, device_id: str) -> None:
        """Fetch the device's apps for the launcher (again, if they were loaded before)."""
        current = self._apps.get(device_id)
        if current is not None and current.state == "loading":
            return
        apps = AppList(
            current.items if current is not None else None,
            current.icons if current is not None else None,
        )
        self._apps[device_id] = apps
        self._changed()
        self.runner.run(self._load_apps(device_id, apps))

    def launch_app(self, device_id: str, app_id: str) -> None:
        self.runner.run(self._backend.launch_app(device_id, app_id))

    def set_text(self, device_id: str, text: str) -> None:
        """Replace the text in the device's text field. Typing sends often, so only the newest
        text waits while one is on its way, and texts arrive in order."""
        self._text_pending[device_id] = text[:MAX_TEXT]
        if device_id not in self._text_sending:
            self._text_sending.add(device_id)
            self.runner.run(self._send_text(device_id))

    def set_appearance(
        self, theme: str | None = None, background: str | None = None, **changes: Any
    ) -> None:
        """Change some appearance and Advanced settings; the rest stay as they are."""
        if theme is not None:
            try:
                changes["theme"] = Theme(theme)
            except ValueError:
                _LOGGER.warning("Ignoring an unknown appearance choice")
                return
        if background is not None:
            changes["background"] = background
        try:
            appearance = dataclasses.replace(self.appearance, **changes)
        except (ValueError, TypeError):
            _LOGGER.warning("Ignoring an unknown appearance choice")
            return
        self.runner.run(self._backend.set_appearance(appearance))

    def _set_appearance_from(self, f: Fields) -> None:
        theme, background = f.text("theme"), f.text("background")
        if (f.has("theme") and theme is None) or (f.has("background") and background is None):
            return
        changes: dict[str, Any] = {}
        for key, field in _APPEARANCE_FLAGS.items():
            if f.has(key):
                value = f.flag(key)
                if value is None:
                    return
                changes[field] = value
        if f.has("photoBlur"):
            blur = f.integer("photoBlur")
            if blur is None:
                return
            changes["photo_blur"] = blur
        self.set_appearance(theme, background, **changes)

    def handle(self, command: dict[str, Any]) -> None:
        """Run one command from the front end. Unknown or malformed commands are ignored."""
        if not self._table.handle(command):
            _LOGGER.debug("Ignoring an unknown command")

    def command_kinds(self) -> frozenset[str]:
        """Every command the window may send (`Command` in web/src/types.ts)."""
        return self._table.kinds()

    def _commands_table(self) -> CommandTable:
        table = CommandTable()
        self._device_commands(table)
        self._window_commands(table)
        self.audio.register(table)
        return table

    def _device_commands(self, table: CommandTable) -> None:
        """Cards, pairing, the remote, the launcher and typing."""
        table.on_id("activate", self.activate)
        table.on_id("connect", self.connect)
        table.on_id("disconnect", self.disconnect)
        table.on_id("pair", self._pair_command)
        table.on_id("openDevice", self.open_device)
        table.on_id("loadApps", self.load_apps)

        def submit_pin(f: Fields) -> None:
            pin = f.text("pin")
            if pin is not None:
                self.pairing.submit_pin(pin)

        def press(f: Fields) -> None:
            device_id = f.text("id")
            key, action = f.choice(RemoteKey, "key"), f.choice(KeyAction, "action", "tap")
            if device_id is not None and key is not None and action is not None:
                self.press(device_id, key, action)

        def media(f: Fields) -> None:
            device_id, command = f.text("id"), f.choice(MediaCommand, "command")
            if device_id is not None and command is not None:
                self.media(device_id, command)

        def set_volume(f: Fields) -> None:
            device_id, level = f.text("id"), f.number("level", 0, 100)
            if device_id is not None and level is not None:
                self.set_volume(device_id, level)

        def set_power(f: Fields) -> None:
            device_id, on = f.text("id"), f.flag("on")
            if device_id is not None and on is not None:
                self.set_power(device_id, on)

        def launch_app(f: Fields) -> None:
            device_id, app_id = f.text("id"), f.text("appId")
            if device_id is not None and app_id is not None:
                self.launch_app(device_id, app_id)

        def set_text(f: Fields) -> None:
            device_id, text = f.text("id"), f.text("text")
            if device_id is not None and text is not None:
                self.set_text(device_id, text)

        def device_audio(f: Fields) -> None:
            device_id, on = f.text("id"), f.flag("on")
            if device_id is not None and on is not None:
                self.set_device_audio(device_id, on)

        table.on("deviceAudio", device_audio)
        table.on("submitPin", submit_pin)
        table.on("cancelPairing", lambda _f: self.pairing.cancel())
        table.on("closePairing", lambda _f: self.pairing.close())
        table.on("press", press)
        table.on("media", media)
        table.on("setVolume", set_volume)
        table.on("setPower", set_power)
        table.on("launchApp", launch_app)
        table.on("setText", set_text)

    def _window_commands(self, table: CommandTable) -> None:
        """Messages, typed commands, music, appearance, the Home bridge and links out."""

        def text_command(action: Callable[[str], None]) -> Callable[[Fields], None]:
            def handler(f: Fields) -> None:
                text = f.text("text")
                if text is not None:
                    action(text)

            return handler

        def music(f: Fields) -> None:
            command = f.choice(MusicCommand, "command")
            if command is not None:
                self.music_command(command)

        def music_seek(f: Fields) -> None:
            position = f.number("position", 0, float("inf"))
            if position is not None:
                self.music_seek(position)

        def set_home_bridge(f: Fields) -> None:
            on = f.flag("on")
            if on is not None:
                self.runner.run(self._backend.set_home_bridge(on))

        def open_update(_f: Fields) -> None:
            if self.update is not None:
                self._open_url(self.update.url)

        def add_address(f: Fields) -> None:
            address = f.text("address", limit=MAX_ADDRESS)
            if address is not None and address.strip() and not self.network.adding:
                self.runner.run(self._backend.add_speaker_address(address.strip()))

        def remove_address(f: Fields) -> None:
            address = f.text("address", limit=MAX_ADDRESS)
            if address is not None:
                self.runner.run(self._backend.remove_speaker_address(address))

        def check_network(_f: Fields) -> None:
            if not self.network.checking:
                self.runner.run(self._backend.check_network())

        def set_password(f: Fields) -> None:
            device_id, password = f.text("id"), f.text("password", limit=MAX_PASSWORD)
            if device_id is not None and password:
                self.runner.run(self._backend.set_speaker_password(device_id, password))

        table.on("dismissMessage", lambda _f: self.dismiss_message())
        table.on("openUpdate", open_update)
        table.on("reportProblem", lambda _f: self.report_problem())
        table.on("addSpeakerAddress", add_address)
        table.on("removeSpeakerAddress", remove_address)
        table.on("checkNetwork", check_network)
        table.on("setSpeakerPassword", set_password)
        table.on("previewCommand", text_command(self.commands.preview))
        table.on("runCommand", text_command(self.commands.run))
        table.on("clearCommand", lambda _f: self.commands.clear())
        table.on("music", music)
        table.on("musicSeek", music_seek)
        table.on("setAppearance", self._set_appearance_from)
        table.on("setHomeBridge", set_home_bridge)

    # Internals

    def _on_event(self, event: BackendEvent) -> None:
        if isinstance(event, DeviceUpdated | DeviceRemoved):
            self.audio.audio = self._backend.audio()  # outputs follow the device list
        match event:
            case DeviceUpdated(device=device):
                self._devices[device.id] = device
            case DeviceRemoved(device_id=device_id):
                self._devices.pop(device_id, None)
                self._controls.pop(device_id, None)
                self._apps.pop(device_id, None)
                if self.pairing.device_id == device_id:
                    self.pairing.close()
            case DiscoveryChanged(active=active):
                self.discovering = active
            case ControlsChanged(device_id=device_id, controls=controls):
                if controls is None:
                    self._controls.pop(device_id, None)
                    self._apps.pop(device_id, None)  # fetch afresh after a reconnect
                else:
                    self._controls[device_id] = controls
            case MusicChanged(music=music):
                self.music = music
            case AppearanceChanged(appearance=appearance):
                self.appearance = appearance
                self._refresh_icons()
            case AudioChanged(audio=audio):
                self.audio.audio = audio
            case HomeUpdated(home=home):
                self.home = home
            case NetworkChanged(network=network):
                self.network = network
            case SendChanged(device_id=device_id, send=send):
                if send is None:
                    self.audio.sends.pop(device_id, None)
                else:
                    self.audio.sends[device_id] = send
        self._changed()

    async def _load_apps(self, device_id: str, apps: AppList) -> None:
        try:
            found = await self._backend.apps(device_id)
        except Exception as error:
            if self._apps.get(device_id) is not apps:
                return  # disconnected or reloaded meanwhile
            apps.state = "failed"
            if isinstance(error, BackendError) and error.code:
                apps.error = {"code": error.code}
            else:
                _LOGGER.error("Loading apps failed: %s", type(error).__name__)
                apps.error = {"code": "taskFailed"}
            self._changed()
            return
        if self._apps.get(device_id) is not apps:
            return
        apps.items = sorted(found, key=lambda app: (app.name.casefold(), app.id))
        apps.state = "ready"
        self._changed()
        if self._icons is not None and self.appearance.app_icons:
            self.runner.run(self._load_icons(device_id, apps))

    async def _load_icons(self, device_id: str, apps: AppList) -> None:
        assert self._icons is not None
        try:
            icons = await self._icons.icons([app.id for app in apps.items])
        except Exception as error:  # icons are a nicety: keep the letters
            _LOGGER.info("Loading app icons failed: %s", type(error).__name__)
            return
        if self._apps.get(device_id) is apps and self.appearance.app_icons:
            apps.icons = icons
            self._changed()

    def _refresh_icons(self) -> None:
        """Follow the app icons setting for lists already on screen."""
        for device_id, apps in list(self._apps.items()):
            if not self.appearance.app_icons:
                apps.icons = {}
            elif self._icons is not None and apps.state == "ready":
                self.runner.run(self._load_icons(device_id, apps))

    async def _send_text(self, device_id: str) -> None:
        try:
            while device_id in self._text_pending:
                text = self._text_pending.pop(device_id)
                await self._backend.set_text(device_id, text)
        finally:
            self._text_pending.pop(device_id, None)  # after a failure, drop what's queued
            self._text_sending.discard(device_id)

    def _on_task_error(self, error: BaseException) -> None:
        if isinstance(error, BackendError) and error.code:
            self.message = {"code": error.code}
        else:
            # Type name only: exception messages can contain addresses (docs/PRIVACY.md).
            _LOGGER.error("UI task failed: %s", type(error).__name__)
            self.message = {"code": "taskFailed"}
        self._changed()

    def _changed(self) -> None:
        for listener in list(self._listeners):
            listener()


_AUDIO_BUTTON = {
    OutputState.OFF: "off",
    OutputState.STARTING: "starting",
    OutputState.WAITING: "starting",
    OutputState.STREAMING: "on",
    OutputState.FAILED: "failed",
    OutputState.DIRECT: "on",
    OutputState.MUTED: "on",  # the PC's own outputs only; never an AirPlay device's
    OutputState.AHEAD: "on",
}


def _device_json(
    device: DeviceSnapshot, controls: ControlsSnapshot | None, apps: AppList | None
) -> dict[str, Any]:
    return {
        "id": device.id,
        "name": device.name,
        "kind": device.kind.value,
        "state": device.state.value,
        "needsPairing": device.needs_pairing,
        "retryIn": device.retry_in,
        "controls": None if controls is None else _controls_json(controls, device.kind),
        "apps": None if apps is None else apps.snapshot(),
    }


def _controls_json(controls: ControlsSnapshot, kind: DeviceKind) -> dict[str, Any]:
    """A TV gets the whole remote. A speaker gets an audio remote only (play, pause, skip and
    volume): HomePods report a touch pad and more, but there's no screen to steer."""
    playing = controls.now_playing
    tv = kind is DeviceKind.APPLE_TV
    return {
        "remote": controls.remote and tv,
        "media": sorted(command.value for command in controls.media),
        "volume": controls.volume.value,
        "volumeLevel": controls.volume_level,
        "power": controls.power,
        "canPower": controls.can_power and tv,
        "apps": controls.apps and tv,
        "textEntry": controls.text_entry and tv,
        "keyboard": controls.keyboard and tv,
        "nowPlaying": None
        if playing is None
        else {
            "state": playing.state,
            "title": playing.title,
            "artist": playing.artist,
            "album": playing.album,
            "series": playing.series,
            "app": playing.app,
            "position": playing.position,
            "totalTime": playing.total_time,
        },
    }


def _music_json(music: MusicSnapshot | None, now: float) -> dict[str, Any] | None:
    """What the PC is playing, with the position as of `now` so the page can count on."""
    if music is None:
        return None
    position = music.position
    if position is not None and music.state == "playing":
        position += max(0.0, now - music.position_at)
    if position is not None and music.duration is not None:
        position = min(position, music.duration)
    return {
        "app": music.app,
        "state": music.state,
        "title": music.title,
        "artist": music.artist,
        "album": music.album,
        "position": None if position is None else round(position, 2),
        "duration": music.duration,
        "commands": sorted(command.value for command in music.commands),
        "canSeek": music.can_seek,
        "artwork": music.artwork,
    }


def _outcome_json(outcome: CommandOutcome | None) -> dict[str, Any] | None:
    if outcome is None:
        return None
    return {
        "status": outcome.status,
        "code": outcome.code,
        "params": dict(outcome.params),
        "suggestions": list(outcome.suggestions),
    }
