"""Redacted diagnostics bundle: a zip a user can attach to a public bug report.

It holds a summary (versions, Windows build, settings, visible devices and their connection
state) and the app's logs. Everything passes through the `Redactor` again on the way in, even
though logs are redacted when written, so a value that slipped through then is caught now.
The credential vault is never included (docs/PRIVACY.md).
"""

from __future__ import annotations

import json
import platform
import sys
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from tandem import __version__
from tandem.engine.models import Device
from tandem.engine.redact import Redactor
from tandem.engine.session import ConnectionState

BUNDLE_PREFIX = "tandem-diagnostics"
# Only these files are ever copied in. Anything else in the log folder is skipped.
_LOG_PATTERNS = ("tandem.log", "tandem.log.*")
_MAX_LOG_BYTES = 5_000_000  # per file; the rotating handler keeps files far smaller


@dataclass(frozen=True, slots=True)
class DeviceSummary:
    device: Device
    state: ConnectionState | None = None


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not installed"


def _device_entry(summary: DeviceSummary, redactor: Redactor) -> dict[str, Any]:
    device = summary.device
    return {
        "name": redactor.add(device.name, "device"),
        "id": redactor.add(device.id, "id"),
        "kind": device.kind.value,
        "model": device.model,
        "services": sorted(s.value for s in device.services),
        "paired": sorted(s.value for s in device.paired),
        "needs_pairing": sorted(s.value for s in device.needs_pairing),
        "connection": summary.state.value if summary.state else None,
    }


def summary(
    redactor: Redactor,
    devices: Sequence[DeviceSummary] = (),
    settings: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The bundle's summary.json content. Names and ids become placeholders."""
    return {
        "created": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "tandem": __version__,
        "python": sys.version.split()[0],
        "pyatv": _package_version("pyatv"),
        "os": platform.platform(),
        "settings": settings or {},
        "devices": [_device_entry(d, redactor) for d in devices],
    }


def _log_files(log_dir: Path | None) -> list[Path]:
    if log_dir is None or not log_dir.is_dir():
        return []
    found: set[Path] = set()
    for pattern in _LOG_PATTERNS:
        found.update(p for p in log_dir.glob(pattern) if p.is_file())
    return sorted(found)


def _read_redacted(path: Path, redactor: Redactor) -> str:
    with path.open("rb") as handle:
        data = handle.read(_MAX_LOG_BYTES)
    text = data.decode("utf-8", errors="replace")
    return "\n".join(redactor.redact(line) for line in text.splitlines()) + "\n"


def write_bundle(
    out_dir: Path,
    redactor: Redactor,
    *,
    devices: Iterable[DeviceSummary] = (),
    settings: dict[str, Any] | None = None,
    log_dir: Path | None = None,
    now: datetime | None = None,
) -> Path:
    """Write the zip into `out_dir` and return its path."""
    now = now or datetime.now(UTC)
    content = summary(redactor, list(devices), settings, now)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{BUNDLE_PREFIX}-{now:%Y%m%d-%H%M%S}.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("summary.json", redactor.redact(json.dumps(content, indent=2)) + "\n")
        for log in _log_files(log_dir):
            bundle.writestr(f"logs/{log.name}", _read_redacted(log, redactor))
        bundle.writestr("README.txt", _README)
    return path


_README = """Tandem diagnostics bundle

Device names, identifiers, addresses, email addresses and user-folder paths have been
replaced with placeholders such as <device-1>. Pairing credentials are never included.
Open the files and check them before you share this bundle.
"""
