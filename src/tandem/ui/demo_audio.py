"""Audio outputs and media sending for `DemoBackend`, with invented devices (docs/PRIVACY.md).

Mixed into `DemoBackend`. Outputs turn on after a short wait, as a real speaker would. Sending
works only to the demo TV, and only once it's connected.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace

from tandem.ui.backend import (
    MAX_DELAY_MS,
    AudioChanged,
    AudioError,
    AudioSnapshot,
    AudioSourceChoice,
    BackendEvent,
    DeviceKind,
    DeviceSnapshot,
    LinkState,
    MediaError,
    OutputKind,
    OutputSnapshot,
    OutputState,
    SendChanged,
    SendSnapshot,
    SendState,
)

# Invented PC outputs. The first is the "Windows default", which echoes with system audio.
DEMO_PC_OUTPUTS = (("demo-pc-speakers", "Speakers"), ("demo-pc-headphones", "Headphones"))
DEMO_DEFAULT_PC_OUTPUT = "demo-pc-speakers"
PAIR_FIRST = "Pair this device first."
NOT_A_TV = "Only an Apple TV can play videos and links."
CONNECT_FIRST = "Connect the TV first."
EMPTY = "Paste a link or choose a file first."


class DemoAudio:
    _sleep: Callable[[float], Awaitable[None]]
    _delay: float
    _publish: Callable[[BackendEvent], None]

    def devices(self) -> list[DeviceSnapshot]: ...

    def _init_audio(self) -> None:
        self._source = AudioSourceChoice.SYSTEM
        self._outputs: dict[str, OutputSnapshot] = {}
        self._sends: dict[str, SendSnapshot] = {}
        self.sent: list[tuple[str, str]] = []

    def audio(self) -> AudioSnapshot:
        outputs: list[OutputSnapshot] = []
        for device in self.devices():
            outputs.append(
                self._outputs.get(device.id)
                or OutputSnapshot(
                    device.id,
                    device.name,
                    OutputKind.AIRPLAY,
                    device_kind=device.kind,
                    needs_pairing=device.needs_pairing,
                )
            )
        for output_id, name in DEMO_PC_OUTPUTS:
            if self._source is AudioSourceChoice.SYSTEM and output_id == DEMO_DEFAULT_PC_OUTPUT:
                continue
            outputs.append(
                self._outputs.get(output_id) or OutputSnapshot(output_id, name, OutputKind.PC)
            )
        outputs.sort(key=lambda o: (o.kind is OutputKind.PC, o.name.casefold(), o.id))
        return AudioSnapshot(self._source, tuple(outputs), self._source is AudioSourceChoice.SYSTEM)

    def send(self, device_id: str) -> SendSnapshot | None:
        return self._sends.get(device_id)

    async def set_output(self, output_id: str, on: bool) -> None:
        output = self._find(output_id)
        if not on:
            self._store(replace(output, state=OutputState.OFF))
            return
        if output.needs_pairing:
            raise AudioError(PAIR_FIRST)
        self._store(replace(output, state=OutputState.STARTING))
        await self._sleep(self._delay / 2)
        if self._find(output_id).state is OutputState.STARTING:
            self._store(replace(self._find(output_id), state=OutputState.STREAMING))

    async def set_output_volume(self, output_id: str, level: float) -> None:
        self._store(replace(self._find(output_id), volume=max(0.0, min(100.0, level))))

    async def set_output_delay(self, output_id: str, delay_ms: int) -> None:
        delay = max(0, min(MAX_DELAY_MS, int(delay_ms)))
        self._store(replace(self._find(output_id), delay_ms=delay))

    async def set_audio_source(self, source: AudioSourceChoice) -> None:
        self._source = source
        if source is AudioSourceChoice.SYSTEM:
            self._outputs.pop(DEMO_DEFAULT_PC_OUTPUT, None)  # it would echo
        self._publish(AudioChanged(self.audio()))

    async def send_media(self, device_id: str, location: str) -> None:
        device = next((d for d in self.devices() if d.id == device_id), None)
        if device is None or device.kind is not DeviceKind.APPLE_TV:
            raise MediaError(NOT_A_TV)
        if device.state is not LinkState.CONNECTED:
            raise MediaError(CONNECT_FIRST)
        location = location.strip()
        if not location:
            raise MediaError(EMPTY)
        self.sent.append((device_id, location))
        title = location.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or "Link"
        self._set_send(device_id, SendSnapshot(SendState.STARTING, title))
        await self._sleep(self._delay / 2)
        self._set_send(device_id, SendSnapshot(SendState.PLAYING, title))

    async def stop_media(self, device_id: str) -> None:
        if self._sends.pop(device_id, None) is not None:
            self._publish(SendChanged(device_id, None))

    def _find(self, output_id: str) -> OutputSnapshot:
        output = next((o for o in self.audio().outputs if o.id == output_id), None)
        if output is None:
            raise AudioError("That speaker is no longer available.")
        return output

    def _store(self, output: OutputSnapshot) -> None:
        self._outputs[output.id] = output
        self._publish(AudioChanged(self.audio()))

    def _set_send(self, device_id: str, send: SendSnapshot) -> None:
        self._sends[device_id] = send
        self._publish(SendChanged(device_id, send))
