"""The Audio and Send to TV panels on the real engine (part of `tandem.bridge`, ADR-0008).

Kept apart from `bridge.py` so each panel's mapping reads on its own. `EngineAudio` is mixed
into `EngineBackend`; it needs the engine, the output preferences and the backend's publisher.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from tandem.engine import pairing as engine_pairing
from tandem.engine.audio import AudioError as EngineAudioError
from tandem.engine.audio import AudioStreamChanged, StreamState
from tandem.engine.audio_hub import is_local
from tandem.engine.media_send import MediaError as EngineMediaError
from tandem.engine.media_send import MediaSendChanged
from tandem.engine.media_send import SendState as EngineSendState
from tandem.engine.output_prefs import OutputPrefsStore
from tandem.engine.registry import DeviceEvent
from tandem.engine.service import AudioSource, Engine, UnknownDeviceError
from tandem.ui import backend as ui

_LOGGER = logging.getLogger(__name__)

# Words the window shows. Safe to show: no names, addresses or paths.
PAIR_FIRST = "Pair this device first."
GONE = "That speaker is no longer available."
NO_AUDIO = "Tandem couldn't send audio there. Make sure it's on and try again."
NO_SEND = "The TV couldn't play that. Try an MP4 or MOV file, or a direct link to one."
NOT_STREAMING = "Turn this output on first."

_STATE = {
    StreamState.STARTING: ui.OutputState.STARTING,
    StreamState.STREAMING: ui.OutputState.STREAMING,
    StreamState.WAITING: ui.OutputState.WAITING,
    StreamState.STOPPED: ui.OutputState.OFF,
    StreamState.FAILED: ui.OutputState.FAILED,
}
_SEND = {
    EngineSendState.STARTING: ui.SendState.STARTING,
    EngineSendState.PLAYING: ui.SendState.PLAYING,
    EngineSendState.ENDED: ui.SendState.ENDED,
    EngineSendState.FAILED: ui.SendState.FAILED,
}


class EngineAudio:
    """Audio outputs, the source choice and media sending, for `EngineBackend`."""

    _engine: Engine
    _publish: Callable[[ui.BackendEvent], None]

    def _init_audio(self, prefs: OutputPrefsStore) -> list[Callable[[], None]]:
        self._prefs = prefs
        self._failed: set[str] = set()
        self._sends: dict[str, ui.SendSnapshot] = {}
        bus = self._engine.bus
        return [
            bus.subscribe(AudioStreamChanged, self._on_stream),
            bus.subscribe(MediaSendChanged, self._on_send),
            bus.subscribe(DeviceEvent, lambda _event: self._audio_changed()),
        ]

    # Reading

    def audio(self) -> ui.AudioSnapshot:
        on = self._engine.outputs_on()
        outputs: list[ui.OutputSnapshot] = []
        for device in self._engine.registry.devices():
            if not device.can_play_audio:
                continue
            outputs.append(
                self._output(
                    device.id,
                    device.name,
                    ui.OutputKind.AIRPLAY,
                    on,
                    device_kind=ui.DeviceKind(device.kind.value),
                    needs_pairing=bool(engine_pairing.services_to_pair(device)),
                )
            )
        available = self._engine.local_outputs()
        for local in available:
            outputs.append(self._output(local.id, local.name, ui.OutputKind.PC, on))
        outputs.sort(key=lambda o: (o.kind is ui.OutputKind.PC, o.name.casefold(), o.id))
        system = self._engine.audio_source is AudioSource.SYSTEM
        return ui.AudioSnapshot(
            source=ui.AudioSourceChoice.SYSTEM if system else ui.AudioSourceChoice.PLAYER,
            outputs=tuple(outputs),
            pc_outputs_hidden=system,
        )

    def send(self, device_id: str) -> ui.SendSnapshot | None:
        return self._sends.get(device_id)

    # Commands

    async def set_output(self, output_id: str, on: bool) -> None:
        if not on:
            self._failed.discard(output_id)
            await self._engine.stop_output(output_id)
            self._audio_changed()
            return
        if not is_local(output_id):
            try:
                device = self._engine.device(output_id)
            except UnknownDeviceError:
                raise ui.AudioError(GONE) from None
            if engine_pairing.services_to_pair(device):
                raise ui.AudioError(PAIR_FIRST)
        prefs = self._prefs.get(output_id)
        self._failed.discard(output_id)
        try:
            await self._engine.start_output(output_id, volume=prefs.volume, delay_ms=prefs.delay_ms)
        except (EngineAudioError, OSError, TimeoutError, ValueError) as exc:
            _LOGGER.info("An output didn't start (%s)", type(exc).__name__)
            self._failed.add(output_id)
            self._audio_changed()
            raise ui.AudioError(NO_AUDIO) from None
        self._audio_changed()

    async def set_output_volume(self, output_id: str, level: float) -> None:
        level = max(0.0, min(100.0, float(level)))
        self._prefs.update(output_id, volume=level)
        if output_id in self._engine.outputs_on():
            try:
                await self._engine.set_output_volume(output_id, level)
            except (EngineAudioError, OSError, TimeoutError) as exc:
                _LOGGER.info("Setting an output's volume failed (%s)", type(exc).__name__)
                raise ui.AudioError(NO_AUDIO) from None
        self._audio_changed()

    async def set_output_delay(self, output_id: str, delay_ms: int) -> None:
        delay_ms = max(0, min(ui.MAX_DELAY_MS, int(delay_ms)))
        self._prefs.update(output_id, delay_ms=delay_ms)
        if output_id in self._engine.outputs_on():
            self._engine.set_output_delay(output_id, delay_ms)
        self._audio_changed()

    async def set_audio_source(self, source: ui.AudioSourceChoice) -> None:
        await self._engine.set_audio_source(AudioSource(source.value))
        self._audio_changed()

    async def send_media(self, device_id: str, location: str) -> None:
        try:
            await self._engine.play_media(device_id, location)
        except EngineMediaError as error:
            raise ui.MediaError(str(error)) from None
        except UnknownDeviceError:
            raise ui.MediaError(GONE) from None
        except (OSError, TimeoutError) as exc:
            _LOGGER.info("Sending media failed (%s)", type(exc).__name__)
            raise ui.MediaError(NO_SEND) from None

    async def stop_media(self, device_id: str) -> None:
        await self._engine.stop_media(device_id)
        if self._sends.pop(device_id, None) is not None:
            self._publish(ui.SendChanged(device_id, None))

    # Engine events

    def _on_stream(self, event: AudioStreamChanged) -> None:
        if event.state is StreamState.FAILED:
            self._failed.add(event.device_id)
        self._audio_changed()

    def _on_send(self, event: MediaSendChanged) -> None:
        send = ui.SendSnapshot(_SEND[event.state], event.title)
        self._sends[event.device_id] = send
        self._publish(ui.SendChanged(event.device_id, send))

    def _audio_changed(self) -> None:
        self._publish(ui.AudioChanged(self.audio()))

    def _output(
        self,
        output_id: str,
        name: str,
        kind: ui.OutputKind,
        on: dict[str, tuple[StreamState, float | None, int]],
        *,
        device_kind: ui.DeviceKind | None = None,
        needs_pairing: bool = False,
    ) -> ui.OutputSnapshot:
        prefs = self._prefs.get(output_id)
        live = on.get(output_id)
        if live is not None:
            state = _STATE[live[0]]
            volume, delay = live[1], live[2]
        else:
            state = ui.OutputState.FAILED if output_id in self._failed else ui.OutputState.OFF
            volume, delay = prefs.volume, prefs.delay_ms
        return ui.OutputSnapshot(
            output_id, name, kind, state, volume, delay, device_kind, needs_pairing
        )
