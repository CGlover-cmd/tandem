from __future__ import annotations

import json
from pathlib import Path

import pytest

from tandem.engine import paths
from tandem.engine.events import EventBus
from tandem.engine.settings import Settings, SettingsChanged, SettingsStore, Theme


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "settings.json"


def test_missing_file_gives_defaults(path: Path) -> None:
    assert SettingsStore(path).load() == Settings()
    assert not path.exists()


def test_round_trip(path: Path) -> None:
    store = SettingsStore(path)
    store.update(theme=Theme.DARK, start_minimized=True, discovery_interval_s=30)
    loaded = SettingsStore(path).load()
    assert loaded == Settings(theme=Theme.DARK, start_minimized=True, discovery_interval_s=30.0)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["theme"] == "dark"


def test_bad_values_fall_back_per_field(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "theme": "purple",
                "start_minimized": "yes",
                "launch_at_startup": True,
                "discovery_interval_s": 1,
                "unknown_key": 5,
            }
        ),
        encoding="utf-8",
    )
    assert SettingsStore(path).load() == Settings(launch_at_startup=True)


def test_numbers_must_not_be_booleans(path: Path) -> None:
    path.write_text(json.dumps({"discovery_interval_s": True}), encoding="utf-8")
    assert SettingsStore(path).load().discovery_interval_s == 10.0


@pytest.mark.parametrize("content", ["not json", "[1, 2]", ""])
def test_unreadable_file_gives_defaults_and_is_kept(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    assert SettingsStore(path).load() == Settings()
    assert path.read_text(encoding="utf-8") == content


def test_update_publishes_change_and_coerces(path: Path) -> None:
    bus = EventBus()
    changes: list[SettingsChanged] = []
    bus.subscribe(SettingsChanged, changes.append)
    store = SettingsStore(path, bus)
    updated = store.update(theme="light")
    assert updated.theme is Theme.LIGHT
    assert changes == [SettingsChanged(updated, Settings())]
    store.update(theme=Theme.LIGHT)  # no change, no event
    assert len(changes) == 1


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"volume": 3}, TypeError),
        ({"theme": "purple"}, ValueError),
        ({"start_minimized": 1}, TypeError),
        ({"discovery_interval_s": 1000}, ValueError),
    ],
)
def test_invalid_updates_raise_and_save_nothing(
    path: Path, changes: dict[str, object], error: type[Exception]
) -> None:
    store = SettingsStore(path)
    with pytest.raises(error):
        store.update(**changes)
    assert not path.exists()
    assert store.settings == Settings()


def test_save_leaves_no_temp_files(path: Path) -> None:
    SettingsStore(path).update(start_minimized=True)
    assert [p.name for p in path.parent.iterdir()] == ["settings.json"]


def test_paths_follow_tandem_home(tandem_home: Path) -> None:
    assert paths.data_dir() == tandem_home
    assert paths.settings_file() == tandem_home / "settings.json"
    assert paths.credentials_file() == tandem_home / "credentials.bin"
    assert paths.log_dir() == tandem_home / "logs"


def test_paths_default_to_local_app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TANDEM_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.data_dir() == tmp_path / "Tandem"
    monkeypatch.delenv("LOCALAPPDATA")
    assert paths.data_dir() == Path.home() / ".tandem"
