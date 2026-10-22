"""UI state and logic, in plain Python (ADR-0010).

The web front end only renders `AppController.snapshot()` and sends commands back, so
everything that needs testing (sorting, the pairing state machine, which action a card
offers) lives here and runs under pytest without a window.

Messages for the user are sent as codes (`{"code": "wrongPin"}`); the front end holds the
words, so translations live in one place. Text that comes from the backend (a
`BackendError`) is safe to show and is passed through as `text`.

Now-playing titles and typed commands are personal: they go to the window only, never to a
log.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Coroutine
from enum import Enum
from typing import Any, TypeVar

from tandem.ui.backend import (
    Appearance,
    AppearanceChanged,
    Backend,
    BackendError,
    BackendEvent,
    CommandOutcome,
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

MAX_COMMAND = 200
"""Longest typed command the window may send; longer text is ignored."""

Problem = dict[str, str]
Listener = Callable[[], None]


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


class CommandBar:
    """The typed command bar (Phase 9a).

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
            outcome = CommandOutcome("failed", "backend", {"text": str(error)})
        finally:
            if attempt == self._attempt:
                self.running = False
        if attempt != self._attempt:
            return
        self.result = outcome
        self.result_for = text
        self._on_change()


class AppController:
    """Everything the window and the tray menu show, and the commands they send."""

    def __init__(
        self,
        backend: Backend,
        *,
        demo_mode: bool = False,
        reduce_motion: bool = False,
    ) -> None:
        self._backend = backend
        self.demo_mode = demo_mode
        self.reduce_motion = reduce_motion
        self.discovering = False
        self.message: Problem | None = None
        self.appearance = backend.appearance()
        self.runner = TaskRunner(self._on_task_error)
        self._devices: dict[str, DeviceSnapshot] = {}
        self._controls: dict[str, ControlsSnapshot] = {}
        self._listeners: list[Listener] = []
        self.pairing = PairingController(
            backend, self.runner, on_change=self._changed, on_paired=self.connect
        )
        self.commands = CommandBar(backend, self.runner, on_change=self._changed)
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
            "devices": [_device_json(d, self._controls.get(d.id)) for d in self.devices()],
            "discovering": self.discovering,
            "pairing": self.pairing.snapshot(),
            "commands": self.commands.snapshot(),
            "message": self.message,
            "appearance": {
                "theme": self.appearance.theme.value,
                "background": self.appearance.background,
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

    def set_appearance(self, theme: str, background: str) -> None:
        try:
            appearance = Appearance(Theme(theme), background)
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
        elif kind == "previewCommand" and isinstance(command.get("text"), str):
            self.commands.preview(command["text"])
        elif kind == "runCommand" and isinstance(command.get("text"), str):
            self.commands.run(command["text"])
        elif kind == "clearCommand":
            self.commands.clear()
        elif kind == "setAppearance":
            theme = command.get("theme", self.appearance.theme.value)
            background = command.get("background", self.appearance.background)
            if isinstance(theme, str) and isinstance(background, str):
                self.set_appearance(theme, background)
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
                if self.pairing.device_id == device_id:
                    self.pairing.close()
            case DiscoveryChanged(active=active):
                self.discovering = active
            case ControlsChanged(device_id=device_id, controls=controls):
                if controls is None:
                    self._controls.pop(device_id, None)
                else:
                    self._controls[device_id] = controls
            case AppearanceChanged(appearance=appearance):
                self.appearance = appearance
        self._changed()

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


def _device_json(device: DeviceSnapshot, controls: ControlsSnapshot | None) -> dict[str, Any]:
    return {
        "id": device.id,
        "name": device.name,
        "kind": device.kind.value,
        "state": device.state.value,
        "needsPairing": device.needs_pairing,
        "retryIn": device.retry_in,
        "controls": None if controls is None else _controls_json(controls),
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


def _outcome_json(outcome: CommandOutcome | None) -> dict[str, Any] | None:
    if outcome is None:
        return None
    return {
        "status": outcome.status,
        "code": outcome.code,
        "params": dict(outcome.params),
        "suggestions": list(outcome.suggestions),
    }


E = TypeVar("E", bound=Enum)


def _enum(kind: type[E], value: object) -> E | None:
    try:
        return kind(value)
    except ValueError:
        return None
