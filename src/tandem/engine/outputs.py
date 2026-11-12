"""Audio outputs as the user sees them (Phases 4, 5 and 1.2; review A3).

`AudioHub` streams; this module keeps what the user chose and what they see: which outputs are
on, each one's saved volume and delay, which are starting or failed (and why), the outputs used
most recently, speaker groups, "turn my speakers back on" and automatic line-up. The window,
the command bar, the Home bridge and the developer tool all switch outputs here, so each gets
the saved volume and delay and the same failure handling.

Changes are announced with `OutputsChanged` on the engine's bus. Output ids of AirPlay devices
are device ids (private): never log them.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from tandem.engine import lineup
from tandem.engine import pairing as engine_pairing
from tandem.engine.audio import AudioError as EngineAudioError
from tandem.engine.audio import AudioStreamChanged, StreamState
from tandem.engine.audio_hub import is_local
from tandem.engine.events import Event
from tandem.engine.models import Device, DeviceKind
from tandem.engine.output_groups import GroupStore, OutputGroup
from tandem.engine.output_prefs import OutputPrefsStore
from tandem.engine.pc_mute import PcMute
from tandem.engine.registry import DeviceEvent, DeviceLost
from tandem.engine.screen_cast import ScreenCastChanged
from tandem.engine.session import ConnectionFailedError, ConnectionStateChanged

if TYPE_CHECKING:
    from tandem.engine.service import Engine

_LOGGER = logging.getLogger(__name__)

MAX_DELAY_MS = 10_000
RECENT = 8
"""How many recently used outputs to remember (for the Home app's audio switch)."""


class OutputKind(Enum):
    AIRPLAY = "airplay"  # an AirPlay device, by its device id
    PC = "pc"  # one of the PC's own sound outputs


class OutputState(Enum):
    OFF = "off"
    STARTING = "starting"
    STREAMING = "streaming"
    WAITING = "waiting"  # the connection dropped; it resumes on reconnect
    FAILED = "failed"
    DIRECT = "direct"  # the PC's default output: Windows plays there itself, not Tandem
    MUTED = "muted"  # the PC's default output, muted by Tandem while AirPlay plays (ADR-0020)
    AHEAD = "ahead"  # the PC's default output, kept on while AirPlay plays: it plays ahead


class OutputProblem(Enum):
    """Why an output couldn't play."""

    UNREACHABLE = "unreachable"  # no answer: off, asleep, or on another network
    ACCESS = "access"  # it answered and refused: the Home app's speaker access setting
    PASSWORD = "password"  # it wants a password (Home app "Require Password"), or another one
    STEREO_PAIR = "stereoPair"  # one half of a stereo pair, which Tandem can't play to yet
    FAILED = "failed"  # anything else


@dataclass(frozen=True, slots=True)
class OutputStatus:
    """One place the sound can go. `name` is shown on screen, never logged."""

    id: str
    name: str
    kind: OutputKind
    state: OutputState = OutputState.OFF
    volume: float | None = None
    """0 to 100; None until the user sets it (the device keeps its own volume)."""
    delay_ms: int = 0
    device_kind: DeviceKind | None = None
    needs_pairing: bool = False
    problem: OutputProblem | None = None
    """Why it couldn't play, while `state` is FAILED."""


class GroupState(Enum):
    OFF = "off"
    ON = "on"  # every member that's around is playing
    PARTLY = "partly"  # some members are playing
    STARTING = "starting"


@dataclass(frozen=True, slots=True)
class GroupStatus:
    id: str
    name: str
    outputs: tuple[str, ...]
    state: GroupState = GroupState.OFF


class LineUpState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    DONE = "done"
    FAILED = "failed"


class LineUpProblem(Enum):
    TOO_FEW = "tooFew"  # fewer than two speakers playing
    NO_MIC = "noMic"
    NOT_HEARD = "notHeard"  # the beeps weren't heard from one speaker
    NOISY = "noisy"


@dataclass(frozen=True, slots=True)
class LineUpStatus:
    """Automatic line-up progress. `output` is the output being measured, or not heard."""

    state: LineUpState = LineUpState.IDLE
    output: str | None = None
    problem: LineUpProblem | None = None


class OutputError(Exception):
    """An output or group couldn't be switched. `reason` says why; `str()` is the reason."""

    GONE = "gone"  # the output is no longer around
    PAIR_FIRST = "pair_first"
    NO_AUDIO = "no_audio"  # it didn't start or didn't take the change
    BAD_GROUP = "bad_group"
    GROUP_GONE = "group_gone"
    GROUP_NONE_PLAYED = "group_none_played"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class OutputsChanged(Event):
    """Something about the outputs, groups or line-up changed: read them again."""


_LIVE = {OutputState.STARTING, OutputState.STREAMING, OutputState.WAITING}
_STATE = {
    StreamState.STARTING: OutputState.STARTING,
    StreamState.STREAMING: OutputState.STREAMING,
    StreamState.WAITING: OutputState.WAITING,
    StreamState.STOPPED: OutputState.OFF,
    StreamState.FAILED: OutputState.FAILED,
}

# Exception type names (from the connection or the stream) that mean "no answer" or "refused".
_UNREACHABLE = {
    "TimeoutError",
    "ConnectionFailedError",
    "ConnectionRefusedError",
    "ConnectionResetError",
    "ConnectionAbortedError",
    "OSError",
    "ConnectionClosed",
    "ConnectionLostError",
}
_REFUSED = {"AuthenticationError", "NotPairedError", "PairingError", "AccessDeniedError"}


def classify(
    reason: str | None, error: BaseException | None, device: Device | None = None
) -> OutputProblem:
    """Why an output couldn't play, from the last connection failure or the error itself, and
    what the device announces (a password, a stereo pair)."""
    names = {reason, None if error is None else type(error).__name__} - {None}
    if (
        device is not None
        and device.password_required
        and (not device.password_set or names & _REFUSED)
    ):
        return OutputProblem.PASSWORD
    if names & _REFUSED:
        return OutputProblem.ACCESS
    if device is not None and device.stereo_pair:
        return OutputProblem.STEREO_PAIR
    if names & _UNREACHABLE or not names:
        return OutputProblem.UNREACHABLE
    return OutputProblem.FAILED


class Outputs:
    def __init__(
        self,
        engine: Engine,
        prefs: OutputPrefsStore | None = None,
        groups: GroupStore | None = None,
        pc_mute: PcMute | None = None,
    ) -> None:
        self._engine = engine
        self.prefs = prefs or OutputPrefsStore(None)
        self.groups = groups or GroupStore(None)
        self.pc_mute = pc_mute or PcMute(None)
        """Mutes the PC's speakers while AirPlay plays (ADR-0020)."""
        self._pc_kept = False
        """The user turned the PC's speakers back on while AirPlay plays (until it stops)."""
        self._pc_wanted = False
        self.recent: list[str] = []
        """Outputs turned on most recently, newest first."""
        self.lineup = LineUpStatus()
        self._starting: set[str] = set()
        """Outputs being turned on: shown as starting at once, before the stream reports."""
        self._failed: dict[str, OutputProblem] = {}
        self._last_reason: dict[str, str] = {}
        """Why each device's last connection attempt failed (an exception type name)."""
        self._restoring: set[str] = set()
        self._wanted: set[str] = set()
        """Outputs the user turned on (and not off) this run, whether or not they started."""
        self._tasks: set[asyncio.Task[None]] = set()
        bus = engine.bus
        self._unsubscribe = [
            bus.subscribe(AudioStreamChanged, self._on_stream),
            bus.subscribe(DeviceEvent, self._on_device),
            bus.subscribe(ConnectionStateChanged, self._on_connection),
            bus.subscribe(ScreenCastChanged, lambda _event: self._sync_pc()),
        ]

    async def close(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe = []
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.pc_mute.apply(False)  # never leave the PC muted behind

    # Reading

    def statuses(self) -> list[OutputStatus]:
        """Every output there is now: AirPlay devices that play audio, the PC's default output
        (while Windows plays there itself), and the PC's other outputs. Not sorted."""
        engine = self._engine
        on = engine.outputs_on()
        found: list[OutputStatus] = []
        for device in engine.registry.devices():
            if device.can_play_audio:
                found.append(
                    self._status(
                        device.id,
                        device.name,
                        OutputKind.AIRPLAY,
                        on,
                        device_kind=device.kind,
                        needs_pairing=bool(engine_pairing.services_to_pair(device)),
                    )
                )
        direct = engine.direct_output()
        if direct is not None:
            delay = self.prefs.get(direct.id).delay_ms
            if self.pc_mute.holding:
                state = OutputState.MUTED
            elif self._pc_kept:
                state = OutputState.AHEAD
            else:
                state = OutputState.DIRECT
            found.append(OutputStatus(direct.id, direct.name, OutputKind.PC, state, None, delay))
        for local in engine.local_outputs():
            found.append(self._status(local.id, local.name, OutputKind.PC, on))
        return found

    def streaming(self) -> list[str]:
        """Outputs playing right now (not starting, not waiting)."""
        return [
            output_id
            for output_id, (state, _volume, _delay) in self._engine.outputs_on().items()
            if state is StreamState.STREAMING
        ]

    def group_statuses(self, statuses: Sequence[OutputStatus] | None = None) -> list[GroupStatus]:
        by_id = {s.id: s for s in (self.statuses() if statuses is None else statuses)}
        result: list[GroupStatus] = []
        for group in self.groups.groups():
            members = [by_id[m] for m in group.outputs if m in by_id]
            live = [m for m in members if m.state in _LIVE]
            if any(m.state is OutputState.STARTING for m in members):
                state = GroupState.STARTING
            elif members and len(live) == len(members):
                state = GroupState.ON
            elif live:
                state = GroupState.PARTLY
            else:
                state = GroupState.OFF
            result.append(GroupStatus(group.id, group.name, group.outputs, state))
        return result

    # Switching

    async def start(self, output_id: str) -> None:
        """Turn an output on with its saved volume and delay (connecting a speaker first).
        Raises `OutputError`."""
        engine = self._engine
        if self._is_direct(output_id):
            self._keep_pc(True)
            return
        if not is_local(output_id):
            device = engine.registry.get(output_id)
            if device is None:
                raise OutputError(OutputError.GONE)
            if engine_pairing.services_to_pair(device):
                raise OutputError(OutputError.PAIR_FIRST)
        prefs = self.prefs.get(output_id)
        self._wanted.add(output_id)
        self._failed.pop(output_id, None)
        self._last_reason.pop(output_id, None)
        self._starting.add(output_id)
        self._changed()  # the switch shows a spinner at once, not after the connection
        try:
            await engine.start_output(output_id, volume=prefs.volume, delay_ms=prefs.delay_ms)
        except (EngineAudioError, ConnectionFailedError, OSError, TimeoutError, ValueError) as exc:
            _LOGGER.info("An output didn't start (%s)", type(exc).__name__)
            self._starting.discard(output_id)  # before the change: "starting" outranks "failed"
            self._failed[output_id] = classify(
                self._last_reason.get(output_id), exc, engine.registry.get(output_id)
            )
            self._changed()
            raise OutputError(OutputError.NO_AUDIO) from None
        finally:
            self._starting.discard(output_id)
        self.prefs.update(output_id, on=True)
        self.recent = [output_id, *(o for o in self.recent if o != output_id)][:RECENT]
        self._changed()

    async def stop(self, output_id: str) -> None:
        if self._is_direct(output_id):
            self._keep_pc(False)
            return
        self._failed.pop(output_id, None)
        self._wanted.discard(output_id)
        self._starting.discard(output_id)
        self.prefs.update(output_id, on=False)
        await self._engine.stop_output(output_id)
        self._changed()

    async def stop_all(self) -> None:
        for output_id in list(self._engine.outputs_on()):
            await self.stop(output_id)

    async def set_volume(self, output_id: str, level: float) -> None:
        level = max(0.0, min(100.0, float(level)))
        self.prefs.update(output_id, volume=level)
        if output_id in self._engine.outputs_on():
            try:
                await self._engine.set_output_volume(output_id, level)
            except (EngineAudioError, OSError, TimeoutError) as exc:
                _LOGGER.info("Setting an output's volume failed (%s)", type(exc).__name__)
                raise OutputError(OutputError.NO_AUDIO) from None
        self._changed()

    def note_volume(self, output_id: str, level: float) -> None:
        """The speaker changed its own volume (its buttons, or the Home app): show and keep
        it, without sending it back."""
        level = max(0.0, min(100.0, float(level)))
        self.prefs.update(output_id, volume=level)
        self._engine.note_output_volume(output_id, level)
        self._changed()

    async def set_delay(self, output_id: str, delay_ms: int) -> None:
        delay_ms = max(0, min(MAX_DELAY_MS, int(delay_ms)))
        self.prefs.update(output_id, delay_ms=delay_ms)
        if output_id in self._engine.outputs_on():
            self._engine.set_output_delay(output_id, delay_ms)
        self._changed()

    # The PC's own speakers while AirPlay plays (ADR-0020)

    def _is_direct(self, output_id: str) -> bool:
        if not is_local(output_id):
            return False
        direct = self._engine.direct_output()
        return direct is not None and direct.id == output_id

    def _keep_pc(self, on: bool) -> None:
        """The default output's switch: on plays the PC too (ahead of AirPlay), off mutes it.
        It only means something while AirPlay plays; otherwise Windows just plays there, and
        turning it on is refused (Tandem sending there too would echo)."""
        if on and not self._pc_kept and not (self.pc_mute.holding or self._airplay_playing()):
            raise OutputError(OutputError.NO_AUDIO)  # Windows plays there: Tandem would echo
        self._pc_kept = on
        self._changed()

    def _airplay_playing(self) -> bool:
        """An AirPlay device plays the PC's sound: a speaker, or a TV the screen is cast to."""
        if self._engine.casting() is not None:
            return True
        return any(
            not is_local(output_id) and state in (StreamState.STREAMING, StreamState.WAITING)
            for output_id, (state, _volume, _delay) in self._engine.outputs_on().items()
        )

    def _sync_pc(self) -> None:
        """Mute the PC's default output while AirPlay plays the PC's own sound, unless the user
        kept it on or turned the setting off; unmute it when AirPlay stops."""
        playing = self._engine.audio_source.value == "system" and self._airplay_playing()
        if not playing:
            self._pc_kept = False
        want = playing and not self._pc_kept and self.pc_mute.enabled
        if not want and not self._pc_wanted and not self.pc_mute.holding:
            return  # nothing to do: don't touch Windows on every change
        self._pc_wanted = want
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def apply() -> None:
            if await self.pc_mute.apply(want):
                self._engine.bus.publish(OutputsChanged())

        task = loop.create_task(apply())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def refresh(self) -> None:
        """Something outside changed what the outputs are (the audio source): announce it."""
        self._changed()

    def set_pc_mute(self, enabled: bool) -> None:
        """The setting changed: mute or unmute now if AirPlay is playing."""
        if enabled != self.pc_mute.enabled:
            self.pc_mute.enabled = enabled
            self._changed()

    # Groups

    def save_group(self, name: str, outputs: Sequence[str]) -> OutputGroup:
        try:
            group = self.groups.save(name, outputs)
        except ValueError:
            raise OutputError(OutputError.BAD_GROUP) from None
        self._changed()
        return group

    def delete_group(self, group_id: str) -> None:
        if self.groups.delete(group_id):
            self._changed()

    async def set_group(self, group_id: str, on: bool) -> None:
        group = self.groups.get(group_id)
        if group is None:
            raise OutputError(OutputError.GROUP_GONE)
        await self.set_members(group.outputs, on)

    async def set_members(self, members: Sequence[str], on: bool) -> None:
        """Turn several outputs on or off together. Fails only if none of them would play."""
        available = {s.id: s for s in self.statuses()}
        targets = [m for m in members if m in available and not available[m].needs_pairing]
        if not targets:
            raise OutputError(OutputError.GROUP_NONE_PLAYED if on else OutputError.GROUP_GONE)
        switch = self.start if on else self.stop
        results = await asyncio.gather(*(switch(m) for m in targets), return_exceptions=True)
        if on and all(isinstance(r, BaseException) for r in results):
            raise OutputError(OutputError.GROUP_NONE_PLAYED)

    def failed(self) -> set[str]:
        """Outputs that failed to play and haven't been switched since."""
        return set(self._failed)

    def refused(self) -> int:
        """How many speakers last failed because they turned Tandem away."""
        return sum(p is OutputProblem.ACCESS for p in self._failed.values())

    def retry_unreachable(self) -> None:
        """The network changed: try again the speakers the user wanted on that didn't answer."""
        for output_id, problem in list(self._failed.items()):
            if problem is OutputProblem.UNREACHABLE and output_id in self._wanted:
                self._restoring.add(output_id)
                self._restore(output_id)

    # Turn my speakers back on

    def restore(self) -> None:
        """Turn back on the outputs the user left on: PC outputs now, speakers as they appear."""
        self._restoring = set(self.prefs.were_on())
        for local in self._engine.local_outputs():
            self._restore(local.id)
        for device in self._engine.registry.devices():
            self._restore(device.id)

    def _restore(self, output_id: str) -> None:
        if output_id not in self._restoring:
            return
        self._restoring.discard(output_id)

        async def turn_on() -> None:
            try:
                await self.start(output_id)
            except OutputError as error:
                _LOGGER.info("A speaker didn't come back on (%s)", error.reason)

        task = asyncio.get_running_loop().create_task(turn_on())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # Automatic line-up

    async def line_up(self) -> None:
        """Measure each playing speaker through the microphone, then set the delays so they
        play together. Progress and problems are in `lineup`."""
        playing = self.streaming()
        if len(playing) < 2:
            self._set_lineup(LineUpState.FAILED, problem=LineUpProblem.TOO_FEW)
            return
        lags: dict[str, int] = {}
        for output_id in playing:
            self._set_lineup(LineUpState.LISTENING, output_id)
            try:
                measured = await self._engine.measure_lag(output_id)
            except (EngineAudioError, OSError) as exc:
                _LOGGER.info("Line-up couldn't listen (%s)", type(exc).__name__)
                self._set_lineup(LineUpState.FAILED, problem=LineUpProblem.NO_MIC)
                return
            if measured.lag_ms is None:
                problem = LineUpProblem.NOISY if measured.noisy else LineUpProblem.NOT_HEARD
                self._set_lineup(LineUpState.FAILED, output_id, problem)
                return
            lags[output_id] = measured.lag_ms
        for output_id, delay_ms in lineup.delays_for(lags).items():
            await self.set_delay(output_id, delay_ms)
        self._set_lineup(LineUpState.DONE)

    def _set_lineup(
        self, state: LineUpState, output: str | None = None, problem: LineUpProblem | None = None
    ) -> None:
        self.lineup = LineUpStatus(state, output, problem)
        self._changed()

    # Events

    def _on_stream(self, event: AudioStreamChanged) -> None:
        if event.state is StreamState.FAILED:
            device = self._engine.registry.get(event.device_id)
            self._failed[event.device_id] = classify(event.reason, None, device)
        self._changed()

    def _on_device(self, event: DeviceEvent) -> None:
        if not isinstance(event, DeviceLost):
            self._restore(event.device.id)
        self._changed()

    def _on_connection(self, event: ConnectionStateChanged) -> None:
        if event.reason is not None:
            self._last_reason[event.device_id] = event.reason

    def _changed(self) -> None:
        self._engine.bus.publish(OutputsChanged())
        self._sync_pc()

    def _status(
        self,
        output_id: str,
        name: str,
        kind: OutputKind,
        on: dict[str, tuple[StreamState, float | None, int]],
        *,
        device_kind: DeviceKind | None = None,
        needs_pairing: bool = False,
    ) -> OutputStatus:
        live = on.get(output_id)
        if live is not None:
            state = _STATE[live[0]]
            volume, delay = live[1], live[2]
        else:
            if output_id in self._starting:
                state = OutputState.STARTING
            elif output_id in self._failed:
                state = OutputState.FAILED
            else:
                state = OutputState.OFF
            prefs = self.prefs.get(output_id)
            volume, delay = prefs.volume, prefs.delay_ms
        problem = self._failed.get(output_id) if state is OutputState.FAILED else None
        return OutputStatus(
            output_id, name, kind, state, volume, delay, device_kind, needs_pairing, problem
        )
