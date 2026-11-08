"""The Audio panel and Send to TV, in plain Python (part of `AppController`, ADR-0010).

Sliders send a value on every move, so only the newest value per output waits while one is
on its way (`Latest`). Media locations (file paths and links) are personal: never logged.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Protocol

from tandem.ui.backend import (
    MAX_DELAY_MS,
    AudioSnapshot,
    AudioSourceChoice,
    Backend,
    OutputSnapshot,
    OutputState,
    SendSnapshot,
)

_LOGGER = logging.getLogger(__name__)

LIVE = frozenset({OutputState.STARTING, OutputState.STREAMING, OutputState.WAITING})
"""Outputs Tandem is sending to (the header's "playing" count). A failed output and the PC's
default output, which Windows plays itself, don't count."""

MAX_LOCATION = 2000
"""Longest link or path the window may send."""


class FilePicker(Protocol):
    async def pick_video(self) -> str | None:
        """Ask for one video file; None if the user cancelled."""
        ...


Runner = Callable[[Coroutine[Any, Any, None]], object]


class Latest:
    """Sends only the newest value per key while one is on its way, in order."""

    def __init__(self, run: Runner, send: Callable[[str, Any], Awaitable[None]]) -> None:
        self._run = run
        self._send = send
        self._pending: dict[str, Any] = {}
        self._sending: set[str] = set()

    def put(self, key: str, value: Any) -> None:
        self._pending[key] = value
        if key not in self._sending:
            self._sending.add(key)
            self._run(self._drain(key))

    async def _drain(self, key: str) -> None:
        try:
            while key in self._pending:
                await self._send(key, self._pending.pop(key))
        finally:
            self._pending.pop(key, None)
            self._sending.discard(key)


class AudioPanel:
    def __init__(
        self,
        backend: Backend,
        run: Runner,
        *,
        on_change: Callable[[], None],
        picker: FilePicker | None = None,
    ) -> None:
        self._backend = backend
        self._run = run
        self._on_change = on_change
        self._picker = picker
        self.audio: AudioSnapshot = backend.audio()
        self.sends: dict[str, SendSnapshot] = {}
        self.picking = False
        self._volumes = Latest(run, backend.set_output_volume)
        self._delays = Latest(run, backend.set_output_delay)

    @property
    def can_pick_files(self) -> bool:
        return self._picker is not None

    def snapshot(self) -> dict[str, Any]:
        return {
            "source": self.audio.source.value,
            "pcOutputsHidden": self.audio.pc_outputs_hidden,
            "outputs": [_output_json(o) for o in self.audio.outputs],
            "streaming": sum(o.state in LIVE for o in self.audio.outputs),
            "canPickFiles": self.can_pick_files,
            "picking": self.picking,
        }

    def send_json(self, device_id: str) -> dict[str, Any] | None:
        send = self.sends.get(device_id)
        return None if send is None else {"state": send.state.value, "title": send.title}

    # Commands

    def handle(self, kind: str, command: dict[str, Any]) -> bool:
        """Run an Audio or Send command. False if `kind` isn't one of them."""
        output_id = command.get("id")
        has_id = isinstance(output_id, str)
        if kind == "setOutput" and has_id and isinstance(command.get("on"), bool):
            self._run(self._backend.set_output(output_id, command["on"]))
        elif kind == "setOutputVolume" and has_id and _number(command.get("level"), 0, 100):
            self._volumes.put(output_id, float(command["level"]))
        elif kind == "setOutputDelay" and has_id and _number(command.get("ms"), 0, MAX_DELAY_MS):
            self._delays.put(output_id, int(command["ms"]))
        elif kind == "setAudioSource":
            try:
                source = AudioSourceChoice(command.get("source"))
            except ValueError:
                return True
            self._run(self._backend.set_audio_source(source))
        elif kind == "sendMedia" and has_id and isinstance(command.get("location"), str):
            location = command["location"].strip()
            if location and len(location) <= MAX_LOCATION:
                self._run(self._backend.send_media(output_id, location))
        elif kind == "pickMedia" and has_id:
            if self._picker is not None and not self.picking:
                self._run(self._pick(output_id))
        elif kind == "stopMedia" and has_id:
            self._run(self._backend.stop_media(output_id))
        elif kind == "allOutputsOff":
            for output in self.audio.outputs:
                if output.state in LIVE or output.state is OutputState.FAILED:
                    self._run(self._backend.set_output(output.id, False))
        else:
            return False
        return True

    async def _pick(self, device_id: str) -> None:
        assert self._picker is not None
        self.picking = True
        self._on_change()
        try:
            path = await self._picker.pick_video()
        finally:
            self.picking = False
            self._on_change()
        if path:
            await self._backend.send_media(device_id, path)


def _output_json(output: OutputSnapshot) -> dict[str, Any]:
    return {
        "id": output.id,
        "name": output.name,
        "kind": output.kind.value,
        "state": output.state.value,
        "volume": output.volume,
        "delayMs": output.delay_ms,
        "deviceKind": None if output.device_kind is None else output.device_kind.value,
        "needsPairing": output.needs_pairing,
        "problem": None if output.problem is None else output.problem.value,
    }


def _number(value: object, low: float, high: float) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and low <= value <= high
