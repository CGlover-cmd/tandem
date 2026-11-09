"""The Audio and Send to TV panels on the real engine (part of `tandem.bridge`, ADR-0008).

The engine's `Outputs` owns the outputs: saved volume and delay, starting and failed states,
groups, "turn my speakers back on" and line-up. This module only maps it to the window's
contract. `EngineAudio` is mixed into `EngineBackend`; it needs the engine and the backend's
publisher.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

from tandem.engine import outputs as eo
from tandem.engine import pairing as engine_pairing
from tandem.engine.media_send import MediaError as EngineMediaError
from tandem.engine.media_send import MediaSendChanged
from tandem.engine.media_send import SendState as EngineSendState
from tandem.engine.service import AudioSource, Engine, UnknownDeviceError
from tandem.ui import backend as ui

_LOGGER = logging.getLogger(__name__)

Problem = ui.Problem
T = TypeVar("T")

_PROBLEM = {
    eo.OutputError.GONE: Problem.SPEAKER_GONE,
    eo.OutputError.PAIR_FIRST: Problem.PAIR_FIRST,
    eo.OutputError.NO_AUDIO: Problem.NO_AUDIO,
    eo.OutputError.BAD_GROUP: Problem.BAD_GROUP,
    eo.OutputError.GROUP_GONE: Problem.GROUP_GONE,
    eo.OutputError.GROUP_NONE_PLAYED: Problem.GROUP_NONE_PLAYED,
}
_MEDIA_PROBLEM = {
    EngineMediaError.NOT_A_TV: Problem.NOT_A_TV,
    EngineMediaError.FILE_GONE: Problem.FILE_GONE,
}
_SEND = {
    EngineSendState.STARTING: ui.SendState.STARTING,
    EngineSendState.PLAYING: ui.SendState.PLAYING,
    EngineSendState.ENDED: ui.SendState.ENDED,
    EngineSendState.FAILED: ui.SendState.FAILED,
}


async def _switch(step: Awaitable[T]) -> T:
    try:
        return await step
    except eo.OutputError as error:
        raise ui.AudioError(_PROBLEM[error.reason]) from None


class EngineAudio:
    """Audio outputs, the source choice and media sending, for `EngineBackend`."""

    _engine: Engine
    _publish: Callable[[ui.BackendEvent], None]

    def _init_audio(self) -> list[Callable[[], None]]:
        self._sends: dict[str, ui.SendSnapshot] = {}
        bus = self._engine.bus
        return [
            bus.subscribe(eo.OutputsChanged, lambda _event: self._audio_changed()),
            bus.subscribe(MediaSendChanged, self._on_send),
        ]

    @property
    def _outputs(self) -> eo.Outputs:
        return self._engine.outputs

    # Reading

    def audio(self) -> ui.AudioSnapshot:
        outputs = self._outputs
        statuses = outputs.statuses()
        snapshots = sorted((_output(s) for s in statuses), key=ui.output_order)
        names = {s.id: s.name for s in statuses}
        line = outputs.lineup
        system = self._engine.audio_source is AudioSource.SYSTEM
        return ui.AudioSnapshot(
            source=ui.AudioSourceChoice.SYSTEM if system else ui.AudioSourceChoice.PLAYER,
            outputs=tuple(snapshots),
            pc_outputs_hidden=system,
            groups=tuple(
                ui.GroupSnapshot(g.id, g.name, g.outputs, ui.GroupState(g.state.value))
                for g in outputs.group_statuses(statuses)
            ),
            lineup=ui.LineUpSnapshot(
                ui.LineUpState(line.state.value),
                None if line.output is None else names.get(line.output),
                None if line.problem is None else ui.LineUpProblem(line.problem.value),
            ),
        )

    def send(self, device_id: str) -> ui.SendSnapshot | None:
        return self._sends.get(device_id)

    # Outputs

    async def set_output(self, output_id: str, on: bool) -> None:
        await _switch(self._outputs.start(output_id) if on else self._outputs.stop(output_id))

    async def set_output_volume(self, output_id: str, level: float) -> None:
        await _switch(self._outputs.set_volume(output_id, level))

    async def set_output_delay(self, output_id: str, delay_ms: int) -> None:
        await _switch(self._outputs.set_delay(output_id, delay_ms))

    async def set_audio_source(self, source: ui.AudioSourceChoice) -> None:
        await self._engine.set_audio_source(AudioSource(source.value))
        self._audio_changed()

    def restore_outputs(self) -> None:
        self._outputs.restore()

    async def line_up(self) -> None:
        await self._outputs.line_up()

    # Speaker groups

    async def save_group(self, name: str, outputs: Sequence[str]) -> None:
        try:
            self._outputs.save_group(name, outputs)
        except eo.OutputError as error:
            raise ui.AudioError(_PROBLEM[error.reason]) from None

    async def delete_group(self, group_id: str) -> None:
        self._outputs.delete_group(group_id)

    async def set_group(self, group_id: str, on: bool) -> None:
        await _switch(self._outputs.set_group(group_id, on))

    # Sending media

    async def send_media(self, device_id: str, location: str) -> None:
        device = self._engine.registry.get(device_id)
        if device is None:
            raise ui.MediaError(Problem.NOT_AVAILABLE)
        if engine_pairing.services_to_pair(device):
            raise ui.MediaError(Problem.PAIR_FIRST)
        if not location.strip():
            raise ui.MediaError(Problem.NO_LOCATION)
        try:
            await self._engine.play_media(device_id, location)
        except EngineMediaError as error:
            raise ui.MediaError(_MEDIA_PROBLEM.get(error.reason, Problem.NO_SEND)) from None
        except UnknownDeviceError:
            raise ui.MediaError(Problem.SPEAKER_GONE) from None
        except (OSError, TimeoutError) as exc:
            _LOGGER.info("Sending media failed (%s)", type(exc).__name__)
            raise ui.MediaError(Problem.NO_SEND) from None

    async def stop_media(self, device_id: str) -> None:
        await self._engine.stop_media(device_id)
        if self._sends.pop(device_id, None) is not None:
            self._publish(ui.SendChanged(device_id, None))

    # Engine events

    def _on_send(self, event: MediaSendChanged) -> None:
        send = ui.SendSnapshot(_SEND[event.state], event.title)
        self._sends[event.device_id] = send
        self._publish(ui.SendChanged(event.device_id, send))

    def _audio_changed(self) -> None:
        self._publish(ui.AudioChanged(self.audio()))


def _output(status: eo.OutputStatus) -> ui.OutputSnapshot:
    return ui.OutputSnapshot(
        status.id,
        status.name,
        ui.OutputKind(status.kind.value),
        ui.OutputState(status.state.value),
        status.volume,
        status.delay_ms,
        None if status.device_kind is None else ui.DeviceKind(status.device_kind.value),
        status.needs_pairing,
        None if status.problem is None else ui.OutputProblem(status.problem.value),
    )
