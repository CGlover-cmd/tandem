"""1.2.0: speakers come back on at start, scanning slows down while idle, diagnostics."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from conftest import FakeBackend, FakeClock, ManualSleep, make_device
from tandem import bridge
from tandem.engine import discovery as discovery_module
from tandem.engine.discovery import Discovery
from tandem.engine.events import EventBus
from tandem.engine.output_prefs import OutputPrefsStore
from tandem.engine.registry import DeviceRegistry
from tandem.engine.service import Engine
from tandem.engine.settings import SettingsStore
from tandem.ui import backend as ui

SPEAKER = make_device()


async def _until(predicate: object, rounds: int = 200) -> None:
    for _ in range(rounds):
        if predicate():  # type: ignore[operator]
            return
        await asyncio.sleep(0)
    raise AssertionError("condition not reached")


async def test_speakers_left_on_come_back_on(tmp_path: Path, manual_sleep: ManualSleep) -> None:
    prefs_file = tmp_path / "outputs.json"
    prefs_file.write_text(
        json.dumps({SPEAKER.id: {"volume": 30, "delay_ms": 0, "on": True}}), encoding="utf-8"
    )
    prefs = OutputPrefsStore(prefs_file)
    prefs.load()
    assert prefs.were_on() == [SPEAKER.id]
    bus = EventBus()
    settings = SettingsStore(tmp_path / "settings.json", bus)
    settings.update(restore_outputs=True)
    fake = FakeBackend([SPEAKER])
    engine = Engine(fake, bus=bus, sleep=manual_sleep, discovery_interval=60.0, output_prefs=prefs)
    backend = bridge.EngineBackend(engine, settings)
    await backend.start()
    await _until(lambda: SPEAKER.id in engine.outputs_on())
    assert engine.outputs_on()[SPEAKER.id][1] == 30  # with its saved volume

    await backend.set_output(SPEAKER.id, False)  # turned off by hand: stays off next time
    assert not _reloaded(prefs_file)
    manual_sleep.release()
    await backend.stop()


def _reloaded(path: Path) -> bool:
    store = OutputPrefsStore(path)
    store.load()
    return store.get(SPEAKER.id).on


async def test_speakers_stay_off_unless_asked(tmp_path: Path, manual_sleep: ManualSleep) -> None:
    prefs_file = tmp_path / "outputs.json"
    prefs_file.write_text(json.dumps({SPEAKER.id: {"on": True}}), encoding="utf-8")
    prefs = OutputPrefsStore(prefs_file)
    prefs.load()
    bus = EventBus()
    engine = Engine(
        FakeBackend([SPEAKER]),
        bus=bus,
        sleep=manual_sleep,
        discovery_interval=60.0,
        output_prefs=prefs,
    )
    backend = bridge.EngineBackend(engine, SettingsStore(tmp_path / "settings.json", bus))
    await backend.start()
    for _ in range(20):
        await asyncio.sleep(0)
    assert not engine.outputs_on()
    manual_sleep.release()
    await backend.stop()


async def test_hidden_and_silent_scans_less_often(
    tmp_path: Path, manual_sleep: ManualSleep
) -> None:
    bus = EventBus()
    engine = Engine(FakeBackend([SPEAKER]), bus=bus, sleep=manual_sleep, discovery_interval=10.0)
    backend = bridge.EngineBackend(engine, SettingsStore(tmp_path / "settings.json", bus))
    await backend.start()
    await backend.set_window_visible(False)
    assert engine.discovery.idle
    await backend.set_window_visible(True)
    assert not engine.discovery.idle

    await backend.set_output(SPEAKER.id, True)  # playing: keep scanning while hidden
    await backend.set_window_visible(False)
    assert not engine.discovery.idle
    manual_sleep.release()
    await backend.stop()


async def test_idle_discovery_waits_longer_and_keeps_devices(
    clock: FakeClock, manual_sleep: ManualSleep
) -> None:
    registry = DeviceRegistry(EventBus(), clock=clock)

    async def scanner(_timeout: float) -> list[object]:
        return [SPEAKER]

    discovery = Discovery(registry, scanner, interval=10.0, sleep=manual_sleep)  # type: ignore[arg-type]
    await discovery.set_idle(True)
    discovery.start()
    await manual_sleep.until(1)
    assert manual_sleep.delays[-1] == discovery_module.IDLE_INTERVAL
    clock.now += discovery_module.IDLE_INTERVAL + 5
    manual_sleep.release()
    await manual_sleep.until(2)
    assert registry.get(SPEAKER.id) is not None  # not "lost" for being scanned less often

    await discovery.set_idle(False)  # waking up scans at once
    await manual_sleep.until(3)
    assert manual_sleep.delays[-1] == 10.0
    await discovery.stop()


async def test_diagnostics_zip_for_a_problem_report(
    tmp_path: Path, manual_sleep: ManualSleep, monkeypatch: object
) -> None:
    import pytest

    mp: pytest.MonkeyPatch = monkeypatch  # type: ignore[assignment]
    mp.setenv("TANDEM_HOME", str(tmp_path / "home"))
    bus = EventBus()
    engine = Engine(FakeBackend([SPEAKER]), bus=bus, sleep=manual_sleep)
    backend = bridge.EngineBackend(engine, SettingsStore(tmp_path / "settings.json", bus))
    bundle = await backend.write_diagnostics()
    assert bundle is not None
    assert bundle.is_file()
    assert bundle.parent == tmp_path / "home" / "diagnostics"
    assert isinstance(ui.Appearance().update_check, bool)
    manual_sleep.release()
    await engine.close()
