"""Run typed commands (Phase 9a) on the engine.

`CommandDispatcher` parses a line with `tandem.engine.commands`, picks a device when the
command didn't name one, checks the device can do it right now, and runs it. It reaches
devices through `CommandServices`, a small protocol: `EngineCommandServices` provides it on
`Engine`, and the demo window provides it on invented devices (`tandem.bridge`).

`preview` does everything but the last step, so the window can say what Enter will do while
the user types. Results are a code plus parameters (`CommandResult`); the window holds the
words. Parameters hold device and app names, so results are shown on screen and never logged.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from tandem.engine import control as ec
from tandem.engine.commands import (
    Help,
    Media,
    MediaAction,
    OpenApp,
    Problem,
    ProblemCode,
    SendAudio,
    SetVolume,
    StepVolume,
    StopStreaming,
    SwitchTarget,
    Target,
    Turn,
    examples,
    match_name,
    parse,
)
from tandem.engine.service import Engine

_LOGGER = logging.getLogger(__name__)


class Outcome(Enum):
    READY = "ready"
    """Preview only: understood; running it would do `code`."""
    DONE = "done"
    HELP = "help"
    NEEDS_INFO = "needsInfo"
    """Which device or app? `suggestions` holds whole commands to pick from."""
    NOT_UNDERSTOOD = "notUnderstood"
    NOT_AVAILABLE = "notAvailable"
    """Understood, but it can't be done here or right now."""
    FAILED = "failed"


class Code:
    """What a result is about. The window turns each code into words."""

    # Actions (READY and DONE)
    PLAY = "play"
    PAUSE = "pause"
    NEXT = "next"
    PREVIOUS = "previous"
    VOLUME_SET = "volumeSet"
    VOLUME_UP = "volumeUp"
    VOLUME_DOWN = "volumeDown"
    OPEN_APP = "openApp"
    POWER_ON = "powerOn"
    POWER_OFF = "powerOff"
    SWITCH_ON = "switchOn"
    SWITCH_OFF = "switchOff"
    HELP = "help"
    # Problems
    WHICH_DEVICE = "whichDevice"
    NO_DEVICE = "noDevice"
    NOT_CONNECTED = "notConnected"
    CANT_DO_THAT = "cantDoThat"
    NO_VOLUME_LEVEL = "noVolumeLevel"
    NO_VOLUME = "noVolume"
    UNKNOWN_APP = "unknownApp"
    AUDIO_NOT_YET = "audioNotYet"
    SWITCHES_NOT_YET = "switchesNotYet"
    UNKNOWN_SWITCH = "unknownSwitch"
    NO_RESPONSE = "noResponse"


@dataclass(frozen=True, slots=True)
class CommandResult:
    outcome: Outcome
    code: str
    params: dict[str, str] = field(default_factory=dict[str, str])
    """Values for the words, e.g. ``{"device": ..., "level": "30"}``. Private: don't log."""
    suggestions: tuple[str, ...] = ()
    """Whole commands the user can run instead (or, for HELP, examples)."""


# --- What the dispatcher needs from the engine -------------------------------------------


class Ability(Enum):
    PLAY = "play"
    PAUSE = "pause"
    NEXT = "next"
    PREVIOUS = "previous"
    VOLUME_LEVEL = "volume_level"
    VOLUME_STEPS = "volume_steps"
    POWER = "power"
    APPS = "apps"


@dataclass(frozen=True, slots=True)
class TargetState:
    target: Target
    connected: bool = False
    abilities: frozenset[Ability] = frozenset[Ability]()
    playing: bool = False


@dataclass(frozen=True, slots=True)
class SwitchState:
    target: SwitchTarget
    on: bool = False


@dataclass(frozen=True, slots=True)
class AppChoice:
    id: str
    name: str


class ActionError(Exception):
    """A step couldn't run. `code` is one of NOT_CONNECTED, CANT_DO_THAT or NO_RESPONSE."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CommandServices(Protocol):
    """Devices and switches as the dispatcher sees them. Methods raise ActionError."""

    def targets(self) -> Sequence[TargetState]: ...
    def switches(self) -> Sequence[SwitchState]:
        """Switches offered to the Home app; empty while the Home bridge is off."""
        ...

    async def media(self, device_id: str, action: MediaAction) -> None: ...
    async def set_volume(self, device_id: str, level: int) -> None: ...
    async def volume_step(self, device_id: str, up: bool) -> None: ...
    async def set_power(self, device_id: str, on: bool) -> None: ...
    async def apps(self, device_id: str) -> Sequence[AppChoice]: ...
    async def launch(self, device_id: str, app_id: str) -> None: ...
    async def set_switch(self, switch_id: str, on: bool) -> None: ...


# --- The dispatcher ----------------------------------------------------------------------

Step = Callable[[], Awaitable["CommandResult | None"]]
"""Runs a planned command. None means it worked as planned."""


@dataclass(frozen=True, slots=True)
class _Plan:
    code: str
    params: dict[str, str]
    step: Step


_MEDIA_CODE = {
    MediaAction.PLAY: Code.PLAY,
    MediaAction.PAUSE: Code.PAUSE,
    MediaAction.NEXT: Code.NEXT,
    MediaAction.PREVIOUS: Code.PREVIOUS,
}
_MEDIA_ABILITY = {
    MediaAction.PLAY: Ability.PLAY,
    MediaAction.PAUSE: Ability.PAUSE,
    MediaAction.NEXT: Ability.NEXT,
    MediaAction.PREVIOUS: Ability.PREVIOUS,
}
_PROBLEM_OUTCOME = {
    ProblemCode.TOO_LONG: Outcome.NOT_UNDERSTOOD,
    ProblemCode.NOT_UNDERSTOOD: Outcome.NOT_UNDERSTOOD,
    ProblemCode.BAD_VOLUME: Outcome.NOT_UNDERSTOOD,
    ProblemCode.UNKNOWN_DEVICE: Outcome.NEEDS_INFO,
    ProblemCode.AMBIGUOUS_DEVICE: Outcome.NEEDS_INFO,
}
_MAX_APP_SUGGESTIONS = 5


class CommandDispatcher:
    def __init__(self, services: CommandServices) -> None:
        self._services = services

    def preview(self, text: str) -> CommandResult:
        """What running `text` would do, without doing it."""
        plan = self._plan(text)
        if isinstance(plan, CommandResult):
            return plan
        return CommandResult(Outcome.READY, plan.code, plan.params)

    async def run(self, text: str) -> CommandResult:
        plan = self._plan(text)
        if isinstance(plan, CommandResult):
            return plan
        try:
            problem = await plan.step()
        except ActionError as error:
            outcome = Outcome.FAILED if error.code == Code.NO_RESPONSE else Outcome.NOT_AVAILABLE
            return CommandResult(outcome, error.code, plan.params)
        return problem or CommandResult(Outcome.DONE, plan.code, plan.params)

    # Planning

    def _plan(self, text: str) -> _Plan | CommandResult:
        states = list(self._services.targets())
        switches = list(self._services.switches())
        targets = [s.target for s in states]
        parsed = parse(text, targets, [s.target for s in switches])
        if isinstance(parsed, Problem):
            return self._problem(parsed, switches)
        if isinstance(parsed, Help):
            switch_targets = [s.target for s in switches]
            return CommandResult(
                Outcome.HELP, Code.HELP, suggestions=examples(targets, switch_targets)
            )
        if isinstance(parsed, Media):
            return self._media(parsed, states)
        if isinstance(parsed, SetVolume):
            return self._set_volume(parsed, states)
        if isinstance(parsed, StepVolume):
            return self._step_volume(parsed, states)
        if isinstance(parsed, OpenApp):
            return self._open_app(parsed, states)
        if isinstance(parsed, Turn):
            return self._turn(parsed, states)
        # SendAudio and StopStreaming: streaming isn't in the engine yet (Phase 4).
        assert isinstance(parsed, SendAudio | StopStreaming)
        return CommandResult(Outcome.NOT_AVAILABLE, Code.AUDIO_NOT_YET)

    def _problem(self, problem: Problem, switches: list[SwitchState]) -> CommandResult:
        if problem.code is ProblemCode.EMPTY:
            return CommandResult(Outcome.HELP, Code.HELP, suggestions=problem.suggestions)
        params = {"name": problem.subject} if problem.subject else {}
        if problem.code is ProblemCode.UNKNOWN_TARGET:
            if not switches:
                return CommandResult(
                    Outcome.NOT_AVAILABLE, Code.SWITCHES_NOT_YET, params, problem.suggestions
                )
            return CommandResult(
                Outcome.NEEDS_INFO, Code.UNKNOWN_SWITCH, params, problem.suggestions
            )
        return CommandResult(
            _PROBLEM_OUTCOME[problem.code], problem.code.value, params, problem.suggestions
        )

    def _media(self, intent: Media, states: list[TargetState]) -> _Plan | CommandResult:
        action = intent.action

        def prefer(state: TargetState) -> bool:
            # Pause, skip: the one that's playing. Play: one that isn't.
            return state.playing is not (action is MediaAction.PLAY)

        picked = _pick(
            states,
            intent.device,
            _MEDIA_ABILITY[action],
            lambda name: f"{action.value} on {name}",
            prefer,
        )
        if isinstance(picked, CommandResult):
            return picked
        device_id = picked.target.id
        return _Plan(
            _MEDIA_CODE[action],
            {"device": picked.target.name},
            lambda: _done(self._services.media(device_id, action)),
        )

    def _set_volume(self, intent: SetVolume, states: list[TargetState]) -> _Plan | CommandResult:
        level = intent.level
        picked = _pick(
            states,
            intent.device,
            Ability.VOLUME_LEVEL,
            lambda name: f"volume {level} on {name}",
        )
        if isinstance(picked, CommandResult):
            stepper = _volume_fallback(picked, states, intent.device)
            return stepper or picked
        device_id = picked.target.id
        return _Plan(
            Code.VOLUME_SET,
            {"device": picked.target.name, "level": str(level)},
            lambda: _done(self._services.set_volume(device_id, level)),
        )

    def _step_volume(self, intent: StepVolume, states: list[TargetState]) -> _Plan | CommandResult:
        up = intent.up
        word = "up" if up else "down"
        picked = _pick(
            states,
            intent.device,
            Ability.VOLUME_STEPS,
            lambda name: f"volume {word} on {name}",
        )
        if isinstance(picked, CommandResult):
            if picked.code == Code.CANT_DO_THAT:
                return CommandResult(Outcome.NOT_AVAILABLE, Code.NO_VOLUME, picked.params)
            return picked
        device_id = picked.target.id
        return _Plan(
            Code.VOLUME_UP if up else Code.VOLUME_DOWN,
            {"device": picked.target.name},
            lambda: _done(self._services.volume_step(device_id, up)),
        )

    def _open_app(self, intent: OpenApp, states: list[TargetState]) -> _Plan | CommandResult:
        typed = intent.app
        picked = _pick(states, intent.device, Ability.APPS, lambda name: f"open {typed} on {name}")
        if isinstance(picked, CommandResult):
            return picked
        device = picked.target
        params = {"app": typed, "device": device.name}

        async def step() -> CommandResult | None:
            apps = list(await self._services.apps(device.id))
            match = match_name(typed, apps)
            if match.found is None:
                choices = match.candidates or tuple(
                    sorted(apps, key=lambda a: a.name.casefold())[:_MAX_APP_SUGGESTIONS]
                )
                return CommandResult(
                    Outcome.NEEDS_INFO,
                    Code.UNKNOWN_APP,
                    params,
                    tuple(f"open {app.name} on {device.name}" for app in choices),
                )
            await self._services.launch(device.id, match.found.id)
            return CommandResult(
                Outcome.DONE, Code.OPEN_APP, {"app": match.found.name, "device": device.name}
            )

        return _Plan(Code.OPEN_APP, params, step)

    def _turn(self, intent: Turn, states: list[TargetState]) -> _Plan | CommandResult:
        on = intent.on
        target = intent.target
        if isinstance(target, SwitchTarget):
            switch_id = target.id
            return _Plan(
                Code.SWITCH_ON if on else Code.SWITCH_OFF,
                {"switch": target.name},
                lambda: _done(self._services.set_switch(switch_id, on)),
            )
        picked = _pick(states, target, Ability.POWER, lambda name: name)
        if isinstance(picked, CommandResult):
            return picked
        device_id = picked.target.id
        return _Plan(
            Code.POWER_ON if on else Code.POWER_OFF,
            {"device": picked.target.name},
            lambda: _done(self._services.set_power(device_id, on)),
        )


async def _done(step: Awaitable[None]) -> CommandResult | None:
    await step
    return None


def _pick(
    states: list[TargetState],
    device: Target | None,
    ability: Ability,
    command_for: Callable[[str], str],
    prefer: Callable[[TargetState], bool] | None = None,
) -> TargetState | CommandResult:
    """The device to act on: the one named, else the only connected one that can do it
    (or the only preferred one). Otherwise a result asking which, or saying none can."""
    if device is not None:
        state = next((s for s in states if s.target.id == device.id), TargetState(device))
        params = {"device": device.name}
        if not state.connected:
            return CommandResult(Outcome.NOT_AVAILABLE, Code.NOT_CONNECTED, params)
        if ability not in state.abilities:
            return CommandResult(Outcome.NOT_AVAILABLE, Code.CANT_DO_THAT, params)
        return state
    able = [s for s in states if s.connected and ability in s.abilities]
    if len(able) == 1:
        return able[0]
    if not able:
        return CommandResult(Outcome.NOT_AVAILABLE, Code.NO_DEVICE)
    preferred = [s for s in able if prefer(s)] if prefer else []
    if len(preferred) == 1:
        return preferred[0]
    choices = preferred or able
    return CommandResult(
        Outcome.NEEDS_INFO,
        Code.WHICH_DEVICE,
        suggestions=tuple(command_for(s.target.name) for s in choices),
    )


def _volume_fallback(
    problem: CommandResult, states: list[TargetState], device: Target | None
) -> CommandResult | None:
    """A device with volume steps but no level: point at "volume up" instead."""
    if problem.code not in (Code.CANT_DO_THAT, Code.NO_DEVICE):
        return None
    if device is not None:
        candidates = [s for s in states if s.target.id == device.id]
    else:
        candidates = [s for s in states if s.connected]
    steppers = [s for s in candidates if Ability.VOLUME_STEPS in s.abilities]
    if device is None and len(steppers) != 1:
        return None
    if not steppers:
        return CommandResult(Outcome.NOT_AVAILABLE, Code.NO_VOLUME, problem.params)
    name = steppers[0].target.name
    return CommandResult(
        Outcome.NOT_AVAILABLE,
        Code.NO_VOLUME_LEVEL,
        {"device": name},
        (f"volume up on {name}", f"volume down on {name}"),
    )


# --- On the real engine ------------------------------------------------------------------


class EngineCommandServices:
    """`CommandServices` on `Engine`: devices from the registry, actions on their controls."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def targets(self) -> list[TargetState]:
        states: list[TargetState] = []
        for device in self._engine.registry.devices():
            target = Target(device.id, device.name, device.kind)
            controls = self._engine.controls(device.id)
            if not controls.connected:
                states.append(TargetState(target))
                continue
            status = controls.status()
            states.append(
                TargetState(
                    target,
                    connected=True,
                    abilities=abilities(status),
                    playing=status.now_playing.state is ec.PlayState.PLAYING,
                )
            )
        return states

    def switches(self) -> list[SwitchState]:
        return []  # The Home bridge (Phase 9b) adds these.

    async def media(self, device_id: str, action: MediaAction) -> None:
        controls = self._engine.controls(device_id)
        status = controls.status()
        command = _media_command(action, status)
        if command is None:
            return  # already playing, or already paused
        await _act(controls.media(command))

    async def set_volume(self, device_id: str, level: int) -> None:
        await _act(self._engine.controls(device_id).set_volume(float(level)))

    async def volume_step(self, device_id: str, up: bool) -> None:
        controls = self._engine.controls(device_id)
        await _act(controls.volume_up() if up else controls.volume_down())

    async def set_power(self, device_id: str, on: bool) -> None:
        await _act(self._engine.controls(device_id).set_power(on))

    async def apps(self, device_id: str) -> list[AppChoice]:
        try:
            apps = await self._engine.controls(device_id).apps()
        except Exception as error:
            raise _action_error(error) from None
        return [AppChoice(app.id, app.name) for app in apps]

    async def launch(self, device_id: str, app_id: str) -> None:
        await _act(self._engine.controls(device_id).launch(app_id))

    async def set_switch(self, switch_id: str, on: bool) -> None:
        raise ActionError(Code.CANT_DO_THAT)


def abilities(status: ec.ControlStatus) -> frozenset[Ability]:
    """What the dispatcher can do with a connected device, from its controls."""
    caps = status.capabilities
    found: set[Ability] = set()
    if caps & {ec.Capability.PLAY, ec.Capability.PLAY_PAUSE}:
        found.add(Ability.PLAY)
    if caps & {ec.Capability.PAUSE, ec.Capability.PLAY_PAUSE}:
        found.add(Ability.PAUSE)
    if ec.Capability.NEXT in caps:
        found.add(Ability.NEXT)
    if ec.Capability.PREVIOUS in caps:
        found.add(Ability.PREVIOUS)
    if ec.Capability.POWER in caps:
        found.add(Ability.POWER)
    if ec.Capability.APPS in caps:
        found.add(Ability.APPS)
    if status.volume_control is ec.VolumeControl.LEVEL:
        found |= {Ability.VOLUME_LEVEL, Ability.VOLUME_STEPS}
    elif status.volume_control is ec.VolumeControl.STEPS:
        found.add(Ability.VOLUME_STEPS)
    return frozenset(found)


def _media_command(action: MediaAction, status: ec.ControlStatus) -> ec.MediaCommand | None:
    """The engine command for an action. Some apps offer only play/pause (a toggle), so
    "pause" on something already paused does nothing rather than start it."""
    caps = status.capabilities
    playing = status.now_playing.state is ec.PlayState.PLAYING
    if action is MediaAction.NEXT:
        return ec.MediaCommand.NEXT
    if action is MediaAction.PREVIOUS:
        return ec.MediaCommand.PREVIOUS
    wanted, exact = (
        (True, ec.Capability.PLAY) if action is MediaAction.PLAY else (False, ec.Capability.PAUSE)
    )
    if exact in caps:
        return ec.MediaCommand.PLAY if wanted else ec.MediaCommand.PAUSE
    if playing is wanted:
        return None
    return ec.MediaCommand.PLAY_PAUSE


async def _act(command: Awaitable[None]) -> None:
    try:
        await command
    except Exception as error:
        raise _action_error(error) from None


def _action_error(error: Exception) -> ActionError:
    if isinstance(error, ec.NotConnectedError):
        return ActionError(Code.NOT_CONNECTED)
    if isinstance(error, ec.UnsupportedError | ValueError):
        return ActionError(Code.CANT_DO_THAT)
    if isinstance(error, ec.ControlError | OSError | TimeoutError):
        # Type name only: exception messages can hold addresses (docs/PRIVACY.md).
        _LOGGER.info("A typed command failed (%s)", type(error).__name__)
        return ActionError(Code.NO_RESPONSE)
    raise error
