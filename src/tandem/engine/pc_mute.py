"""Keep this PC's speakers quiet while AirPlay plays its sound (ADR-0020).

Windows keeps playing on its default output while Tandem sends the same sound to AirPlay, and
AirPlay is always a couple of seconds behind, so the PC sounds like an echo. While the PC's
audio is captured with process loopback (which records the apps before the output's mute),
Tandem can mute that output and AirPlay still gets everything.

`PcMute` does the muting; `Outputs` decides when. It mutes only an output the user hadn't
muted themselves, and puts back only what it muted. The output it muted is written to a small
file first, so if Tandem is stopped before it can unmute, the next start unmutes it.

Output ids here are the PC's own device ids: never logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Protocol, cast

_LOGGER = logging.getLogger(__name__)


class SpeakerMute(Protocol):
    """Mutes Windows' default output (`adapters/endpoint_mute.py`). Calls may block briefly."""

    def available(self) -> bool:
        """Muting is safe now: the capture doesn't follow the output's mute."""
        ...

    def default_output(self) -> str | None: ...
    def muted(self, endpoint: str) -> bool: ...
    def set_muted(self, endpoint: str, on: bool) -> None: ...


class PcMute:
    def __init__(self, speakers: SpeakerMute | None, record: Path | None = None) -> None:
        self.enabled = True
        """The user's setting (Advanced: "Mute this PC while AirPlay plays")."""
        self._speakers = speakers
        self._record = record
        self._held: str | None = None
        """The output Tandem muted, until it unmutes it."""
        self._left: str | None = None
        """An output the user had muted already: left alone until AirPlay stops."""
        self._lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        return self._speakers is not None and self._speakers.available()

    @property
    def holding(self) -> bool:
        """Tandem has the PC's speakers muted right now."""
        return self._held is not None

    async def recover(self) -> None:
        """Unmute the output a previous run muted and couldn't put back (it was stopped)."""
        endpoint = self._read()
        if endpoint is None:
            return
        if self._speakers is not None:
            try:
                await asyncio.to_thread(self._speakers.set_muted, endpoint, False)
            except OSError as exc:
                _LOGGER.info("Couldn't unmute the PC's speakers (%s)", type(exc).__name__)
        self._write(None)

    async def apply(self, want: bool) -> bool:
        """Mute (or unmute) the PC's default output. Returns True if that changed anything."""
        async with self._lock:
            before = self._held
            try:
                if want and self.enabled and self.available:
                    await self._mute()
                else:
                    self._left = None
                    await self._release()
            except OSError as exc:
                _LOGGER.info("Couldn't change the PC's speaker mute (%s)", type(exc).__name__)
            return self._held != before

    async def _mute(self) -> None:
        speakers = self._speakers
        assert speakers is not None
        endpoint = await asyncio.to_thread(speakers.default_output)
        if endpoint == self._held:
            return
        await self._release()  # Windows switched to another output (headphones plugged in)
        if endpoint is None or endpoint == self._left:
            return
        if await asyncio.to_thread(speakers.muted, endpoint):
            self._left = endpoint  # muted already: the user's choice, not ours to undo
            return
        self._write(endpoint)  # first, so a crash after this still unmutes it
        self._held = endpoint
        await asyncio.to_thread(speakers.set_muted, endpoint, True)

    async def _release(self) -> None:
        endpoint, self._held = self._held, None
        if endpoint is None or self._speakers is None:
            return
        try:
            await asyncio.to_thread(self._speakers.set_muted, endpoint, False)
        finally:
            self._write(None)

    def _read(self) -> str | None:
        if self._record is None:
            return None
        try:
            data: object = json.loads(self._record.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            _LOGGER.info("The PC mute record couldn't be read; ignoring it")
            return None
        endpoint = cast("dict[str, object]", data).get("muted") if isinstance(data, dict) else None
        return endpoint if isinstance(endpoint, str) and endpoint else None

    def _write(self, endpoint: str | None) -> None:
        if self._record is None:
            return
        try:
            if endpoint is None:
                self._record.unlink(missing_ok=True)
            else:
                self._record.parent.mkdir(parents=True, exist_ok=True)
                self._record.write_text(json.dumps({"muted": endpoint}), encoding="utf-8")
        except OSError as exc:
            _LOGGER.info("The PC mute record couldn't be saved (%s)", type(exc).__name__)
