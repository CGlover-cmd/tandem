"""The Home bridge on the real engine (part of `tandem.bridge`, ADR-0016).

`EngineHome` is mixed into `EngineBackend` after `EngineAudio`: the Home app's switches drive
the outputs (Audio), the player (Music) and the Apple TV's power (TV), and follow them back.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress

from tandem.engine import control as ec
from tandem.engine.audio import AudioStreamChanged
from tandem.engine.home_bridge import BridgeServer, HomeBridge, HomeChanged
from tandem.engine.models import DeviceKind
from tandem.engine.outputs import OutputError
from tandem.engine.player import PlayerChanged, PlayerState
from tandem.engine.service import AudioSource, Engine
from tandem.engine.settings import SettingsStore
from tandem.ui import backend as ui

_LOGGER = logging.getLogger(__name__)

TV_CONNECT_TIMEOUT = 15.0


class EngineHome:
    _engine: Engine
    _settings: SettingsStore
    _publish: Callable[[ui.BackendEvent], None]

    def _init_home(self, server: Callable[[], BridgeServer] | None) -> list[Callable[[], None]]:
        self._home: HomeBridge | None = None
        if server is not None:
            self._home = HomeBridge(self._engine.bus, server, self)
        bus = self._engine.bus
        return [
            bus.subscribe(HomeChanged, self._on_home),
            bus.subscribe(AudioStreamChanged, lambda _e: self._refresh_home()),
            bus.subscribe(PlayerChanged, lambda _e: self._refresh_home()),
            bus.subscribe(ec.PowerChanged, lambda _e: self._refresh_home()),
        ]

    @property
    def home_bridge(self) -> HomeBridge | None:
        return self._home

    async def _start_home(self) -> None:
        if self._home is not None and self._settings.settings.home_bridge:
            await self._home.start()

    async def _stop_home(self) -> None:
        if self._home is not None:
            await self._home.stop()

    # The UI contract

    def home(self) -> ui.HomeSnapshot:
        if self._home is None:
            return ui.HomeSnapshot()
        status = self._home.status()
        return ui.HomeSnapshot(
            enabled=self._settings.settings.home_bridge,
            running=status.running,
            paired=status.paired,
            setup_code=status.setup_code,
            failed=status.error is not None,
            switches=status.switches,
        )

    async def set_home_bridge(self, on: bool) -> None:
        if self._home is None:
            raise ui.HomeError(ui.Problem.HOME_UNAVAILABLE)
        self._settings.update(home_bridge=on)
        if on:
            await self._home.start()
            if not self._home.running:
                raise ui.HomeError(ui.Problem.HOME_FAILED)
        else:
            await self._home.stop()

    # HomeActions, for the bridge

    def switch_states(self) -> dict[str, bool]:
        engine = self._engine
        tv = self._tv()
        tv_on = False
        if tv is not None:
            controls = engine.controls(tv)
            tv_on = controls.connected and controls.status().power is ec.PowerState.ON
        return {
            "audio": bool(engine.outputs_on()),
            "music": engine.player.status.state is PlayerState.PLAYING,
            "tv": tv_on,
        }

    async def set_switch(self, switch_id: str, on: bool) -> None:
        engine = self._engine
        if switch_id == "audio":
            if not on:
                await engine.outputs.stop_all()
                return
            targets = list(engine.outputs.recent) or self._default_speakers()
            for output_id in targets:
                with suppress(OutputError):
                    await engine.outputs.start(output_id)
        elif switch_id == "music":
            if on:
                await engine.set_audio_source(AudioSource.PLAYER)
                engine.player.play()
            else:
                engine.player.pause()
        elif switch_id == "tv":
            tv = self._tv()
            if tv is None:
                return
            await engine.connect(tv, timeout=TV_CONNECT_TIMEOUT)
            for _ in range(50):  # the controls come up just after the connection
                if engine.controls(tv).connected:
                    break
                await asyncio.sleep(0.1)
            await engine.controls(tv).set_power(on)

    # Internals

    def _tv(self) -> str | None:
        for device in self._engine.registry.devices():
            if device.kind is DeviceKind.APPLE_TV and device.paired:
                return device.id
        return None

    def _default_speakers(self) -> list[str]:
        from tandem.engine import pairing

        return [
            d.id
            for d in self._engine.registry.devices()
            if d.can_play_audio
            and d.kind is not DeviceKind.APPLE_TV
            and not pairing.services_to_pair(d)
        ]

    def _refresh_home(self) -> None:
        if self._home is not None and self._home.running:
            self._home.refresh()

    def _on_home(self, _event: HomeChanged) -> None:
        self._publish(ui.HomeUpdated(self.home()))
