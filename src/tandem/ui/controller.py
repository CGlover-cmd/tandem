"""UI state and logic, in plain Python (ADR-0010).

The web front end only renders `AppController.snapshot()` and sends commands back, so
everything that needs testing (sorting, the pairing state machine, which action a card
offers) lives here and runs under pytest without a window.

Messages for the user are sent as codes (`{"code": "wrongPin"}`); the front end holds the
words, so translations live in one place. Text that comes from the backend (a
`BackendError`) is safe to show and is passed through as `text`.

Now-playing titles are personal: they go to the window only, never to a log.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Coroutine
from enum import Enum
from typing import Any, Protocol, TypeVar

from tandem.ui.backend import (
    MAX_TEXT,
    Appearance,
    AppearanceChanged,
    AppInfo,
    Backend,
    BackendError,
    BackendEvent,
    ControlsChanged,
    ControlsSnapshot,
    DeviceRemoved,
    DeviceSnapshot,
    DeviceUpdated,
    DiscoveryChanged,
    KeyAction,
    LinkState,
    MediaCommand,
    PairingError,
    PairingFlow,
    RemoteKey,
    Theme,
    WrongPinError,
)

_LOGGER = logging.getLogger(__name__)

_PIN = re.compile(r"\d{4}")

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
                self._fail(str(error))
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
                self._fail(str(error))
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

    def _fail(self, text: str) -> None:
        self._flow = None
        self.error = {"code": "pairingFailed", "text": text} if text else {"code": "pairingFailed"}
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


class AppController:
    """Everything the window and the tray menu show, and the commands they send."""

    def __init__(
        self,
        backend: Backend,
        *,
        demo_mode: bool = False,
        reduce_motion: bool = False,
        icons: IconSource | None = None,
    ) -> None:
        self._backend = backend
        self._icons = icons
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
        self.pairing = PairingController(
            backend, self.runner, on_change=self._changed, on_paired=self.connect
        )
        self._unsubscribe: Callable[[], None] | None = None

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
                for d in self.devices()
            ],
            "discovering": self.discovering,
            "pairing": self.pairing.snapshot(),
            "message": self.message,
            "appearance": {
                "theme": self.appearance.theme.value,
                "background": self.appearance.background,
                "appIcons": self.appearance.app_icons,
            },
            "demo": self.demo_mode,
            "reduceMotion": self.reduce_motion,
        }

    # Lifecycle

    async def start(self) -> None:
        self._unsubscribe = self._backend.subscribe(self._on_event)
        for device in self._backend.devices():
            self._devices[device.id] = device
            controls = self._backend.controls(device.id)
            if controls is not None:
                self._controls[device.id] = controls
        self._changed()
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

    def set_appearance(self, theme: str, background: str, app_icons: bool = True) -> None:
        try:
            appearance = Appearance(Theme(theme), background, app_icons)
        except ValueError:
            _LOGGER.warning("Ignoring an unknown appearance choice")
            return
        self.runner.run(self._backend.set_appearance(appearance))

    def handle(self, command: dict[str, Any]) -> None:
        """Run one command from the front end. Unknown or malformed commands are ignored."""
        kind = command.get("type")
        device_id = command.get("id")
        has_id = isinstance(device_id, str)
        if kind == "activate" and has_id:
            self.activate(device_id)
        elif kind == "connect" and has_id:
            self.connect(device_id)
        elif kind == "disconnect" and has_id:
            self.disconnect(device_id)
        elif kind == "pair" and has_id:
            self.pair(device_id)
        elif kind == "submitPin" and isinstance(command.get("pin"), str):
            self.pairing.submit_pin(command["pin"])
        elif kind == "cancelPairing":
            self.pairing.cancel()
        elif kind == "closePairing":
            self.pairing.close()
        elif kind == "dismissMessage":
            self.dismiss_message()
        elif kind == "press" and has_id:
            key, action = (
                _enum(RemoteKey, command.get("key")),
                _enum(KeyAction, command.get("action", "tap")),
            )
            if key is not None and action is not None:
                self.press(device_id, key, action)
        elif kind == "media" and has_id:
            media = _enum(MediaCommand, command.get("command"))
            if media is not None:
                self.media(device_id, media)
        elif kind == "setVolume" and has_id:
            level = command.get("level")
            if isinstance(level, int | float) and not isinstance(level, bool) and 0 <= level <= 100:
                self.set_volume(device_id, float(level))
        elif kind == "setPower" and has_id and isinstance(command.get("on"), bool):
            self.set_power(device_id, command["on"])
        elif kind == "loadApps" and has_id:
            self.load_apps(device_id)
        elif kind == "launchApp" and has_id and isinstance(command.get("appId"), str):
            self.launch_app(device_id, command["appId"])
        elif kind == "setText" and has_id and isinstance(command.get("text"), str):
            self.set_text(device_id, command["text"])
        elif kind == "setAppearance":
            theme = command.get("theme", self.appearance.theme.value)
            background = command.get("background", self.appearance.background)
            app_icons = command.get("appIcons", self.appearance.app_icons)
            if (
                isinstance(theme, str)
                and isinstance(background, str)
                and isinstance(app_icons, bool)
            ):
                self.set_appearance(theme, background, app_icons)
        else:
            _LOGGER.debug("Ignoring an unknown command")

    # Internals

    def _on_event(self, event: BackendEvent) -> None:
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
            case AppearanceChanged(appearance=appearance):
                self.appearance = appearance
                self._refresh_icons()
        self._changed()

    async def _load_apps(self, device_id: str, apps: AppList) -> None:
        try:
            found = await self._backend.apps(device_id)
        except Exception as error:
            if self._apps.get(device_id) is not apps:
                return  # disconnected or reloaded meanwhile
            apps.state = "failed"
            if isinstance(error, BackendError) and str(error):
                apps.error = {"code": "backend", "text": str(error)}
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
        if isinstance(error, BackendError) and str(error):
            self.message = {"code": "backend", "text": str(error)}
        else:
            # Type name only: exception messages can contain addresses (docs/PRIVACY.md).
            _LOGGER.error("UI task failed: %s", type(error).__name__)
            self.message = {"code": "taskFailed"}
        self._changed()

    def _changed(self) -> None:
        for listener in list(self._listeners):
            listener()


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
        "controls": None if controls is None else _controls_json(controls),
        "apps": None if apps is None else apps.snapshot(),
    }


def _controls_json(controls: ControlsSnapshot) -> dict[str, Any]:
    playing = controls.now_playing
    return {
        "remote": controls.remote,
        "media": sorted(command.value for command in controls.media),
        "volume": controls.volume.value,
        "volumeLevel": controls.volume_level,
        "power": controls.power,
        "canPower": controls.can_power,
        "apps": controls.apps,
        "textEntry": controls.text_entry,
        "keyboard": controls.keyboard,
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


E = TypeVar("E", bound=Enum)


def _enum(kind: type[E], value: object) -> E | None:
    try:
        return kind(value)
    except ValueError:
        return None
