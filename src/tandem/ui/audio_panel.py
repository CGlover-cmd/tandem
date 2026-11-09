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
from tandem.ui.window_commands import CommandTable, Fields

_LOGGER = logging.getLogger(__name__)

LIVE = frozenset({OutputState.STARTING, OutputState.STREAMING, OutputState.WAITING})
"""Outputs Tandem is sending to (the header's "playing" count). A failed output and the PC's
default output, which Windows plays itself, don't count."""

MAX_GROUP_NAME = 40

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
            "lineup": {
                "state": self.audio.lineup.state.value,
                "output": self.audio.lineup.output,
                "problem": None
                if self.audio.lineup.problem is None
                else self.audio.lineup.problem.value,
            },
            "groups": [
                {"id": g.id, "name": g.name, "outputs": list(g.outputs), "state": g.state.value}
                for g in self.audio.groups
            ],
            "streaming": sum(o.state in LIVE for o in self.audio.outputs),
            "canPickFiles": self.can_pick_files,
            "picking": self.picking,
        }

    def send_json(self, device_id: str) -> dict[str, Any] | None:
        send = self.sends.get(device_id)
        return None if send is None else {"state": send.state.value, "title": send.title}

    # Commands

    def register(self, table: CommandTable) -> None:
        """The Audio and Send to TV panels' commands."""
        backend, run = self._backend, self._run

        def set_output(f: Fields) -> None:
            output_id, on = f.text("id"), f.flag("on")
            if output_id is not None and on is not None:
                run(backend.set_output(output_id, on))

        def set_volume(f: Fields) -> None:
            output_id, level = f.text("id"), f.number("level", 0, 100)
            if output_id is not None and level is not None:
                self._volumes.put(output_id, level)

        def set_delay(f: Fields) -> None:
            output_id, ms = f.text("id"), f.number("ms", 0, MAX_DELAY_MS)
            if output_id is not None and ms is not None:
                self._delays.put(output_id, int(ms))

        def set_source(f: Fields) -> None:
            source = f.choice(AudioSourceChoice, "source")
            if source is not None:
                run(backend.set_audio_source(source))

        def send_media(f: Fields) -> None:
            device_id, location = f.text("id"), f.text("location", limit=MAX_LOCATION)
            if device_id is not None and location is not None and location.strip():
                run(backend.send_media(device_id, location.strip()))

        def pick_media(device_id: str) -> None:
            if self._picker is not None and not self.picking:
                run(self._pick(device_id))

        def save_group(f: Fields) -> None:
            name, outputs = f.text("name"), f.texts("outputs", limit=50)
            if name is not None and outputs is not None:
                run(backend.save_group(name[:MAX_GROUP_NAME], outputs))

        def set_group(f: Fields) -> None:
            group_id, on = f.text("id"), f.flag("on")
            if group_id is not None and on is not None:
                run(backend.set_group(group_id, on))

        def line_up(_f: Fields) -> None:
            if self.audio.lineup.state.value != "listening":
                run(backend.line_up())

        def all_off(_f: Fields) -> None:
            for output in self.audio.outputs:
                if output.state in LIVE or output.state is OutputState.FAILED:
                    run(backend.set_output(output.id, False))

        table.on("setOutput", set_output)
        table.on("setOutputVolume", set_volume)
        table.on("setOutputDelay", set_delay)
        table.on("setAudioSource", set_source)
        table.on("sendMedia", send_media)
        table.on_id("pickMedia", pick_media)
        table.on_id("stopMedia", lambda device_id: run(backend.stop_media(device_id)))
        table.on("saveGroup", save_group)
        table.on_id("deleteGroup", lambda group_id: run(backend.delete_group(group_id)))
        table.on("setGroup", set_group)
        table.on("lineUp", line_up)
        table.on("allOutputsOff", all_off)

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
