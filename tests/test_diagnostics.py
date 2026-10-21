from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from conftest import FakeBackend, make_device
from tandem import cli
from tandem.engine import diagnostics
from tandem.engine.diagnostics import DeviceSummary
from tandem.engine.redact import Redactor
from tandem.engine.service import Engine
from tandem.engine.session import ConnectionState

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
SPEAKER = make_device()


def _open(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as bundle:
        return {name: bundle.read(name).decode("utf-8") for name in bundle.namelist()}


def test_bundle_contents_are_redacted(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    # A line that somehow escaped redaction when it was written.
    (logs / "tandem.log").write_text(
        '{"msg": "Living Room Speaker at 192.0.2.10"}\n', encoding="utf-8"
    )
    (logs / "tandem.log.1").write_text('{"msg": "older"}\n', encoding="utf-8")
    (logs / "notes.txt").write_text("not a log", encoding="utf-8")
    (tmp_path / "credentials.bin").write_bytes(b"secret")

    path = diagnostics.write_bundle(
        tmp_path / "out",
        Redactor(),
        devices=[DeviceSummary(SPEAKER, ConnectionState.CONNECTED)],
        settings={"theme": "dark"},
        log_dir=logs,
        now=NOW,
    )
    assert path.name == "tandem-diagnostics-20260102-030405.zip"
    files = _open(path)
    assert sorted(files) == ["README.txt", "logs/tandem.log", "logs/tandem.log.1", "summary.json"]
    everything = "".join(files.values())
    assert "Living Room Speaker" not in everything
    assert "192.0.2.10" not in everything
    assert SPEAKER.id not in everything
    assert "<device-1> at <ip-1>" in files["logs/tandem.log"]

    summary = json.loads(files["summary.json"])
    assert summary["created"] == "2026-01-02T03:04:05+00:00"
    assert summary["settings"] == {"theme": "dark"}
    (device,) = summary["devices"]
    assert device == {
        "name": "<device-1>",
        "id": "<id-1>",
        "kind": "homepod",
        "model": "HomePod mini",
        "services": ["airplay", "raop"],
        "paired": [],
        "needs_pairing": [],
        "connection": "connected",
    }
    assert summary["pyatv"]
    assert summary["os"]


def test_bundle_without_logs(tmp_path: Path) -> None:
    path = diagnostics.write_bundle(tmp_path, Redactor(), log_dir=tmp_path / "missing", now=NOW)
    assert sorted(_open(path)) == ["README.txt", "summary.json"]


def test_unknown_package_version() -> None:
    assert diagnostics._package_version("no-such-package-tandem") == "not installed"  # pyright: ignore[reportPrivateUsage]


async def test_engine_bundle_includes_connection_state(tmp_path: Path) -> None:
    backend = FakeBackend([SPEAKER, make_device(id="AA:BB:CC:00:00:03", name="Porch Speaker")])
    engine = Engine(backend)
    await engine.scan()
    await engine.connect(SPEAKER.id, timeout=1)
    path = engine.diagnostics(tmp_path)
    await engine.close()
    states = {d["connection"] for d in json.loads(_open(path)["summary.json"])["devices"]}
    assert states == {"connected", None}


def test_diagnose_command(tandem_home: Path) -> None:
    out = io.StringIO()
    backend = FakeBackend([SPEAKER])
    code = cli.main(
        ["diagnose", "--out", str(tandem_home / "bundles")],
        backend_factory=lambda: backend,
        out=out,
    )
    assert code == 0
    (bundle,) = (tandem_home / "bundles").glob("tandem-diagnostics-*.zip")
    files = _open(bundle)
    assert "Living Room Speaker" not in "".join(files.values())
    assert "Wrote" in out.getvalue()
    assert "Check its contents" in out.getvalue()
