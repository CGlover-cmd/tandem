"""Build local/denylist.txt from this machine's private details.

Collects device names, addresses and identifiers from local discovery scans, plus the
computer name, Windows username, git identity and Wi-Fi network name. Existing entries
are kept, so hand-added terms survive re-runs. Nothing is printed except a count.

Usage: python tools/build_denylist.py [SCAN_JSON ...]
       (defaults to every local/*scan*.json)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL = REPO_ROOT / "local"
DENYLIST = LOCAL / "denylist.txt"

# Factory default device names identify nobody and appear throughout the docs.
GENERIC_NAMES = {"apple tv", "apple tv 4k", "homepod", "homepod mini"}


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def from_scan(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    terms: set[str] = set()
    for dev in data.get("devices", []):
        for key in ("name", "address", "identifier"):
            if dev.get(key):
                terms.add(str(dev[key]))
        terms.update(str(i) for i in dev.get("all_identifiers", []) if i)
        for service in dev.get("services", []):
            if service.get("identifier"):
                terms.add(str(service["identifier"]))
    return terms


def from_machine() -> set[str]:
    terms = {os.environ.get("COMPUTERNAME", ""), os.environ.get("USERNAME", "")}
    for key in ("user.email", "user.name"):
        terms.add(_run(["git", "config", "--global", key]).strip())
    if sys.platform == "win32":
        for match in re.finditer(r"^\s*SSID\s*:\s*(.+)$", _run(["netsh", "wlan", "show", "interfaces"]), re.M):
            terms.add(match.group(1).strip())
    return terms


def main(argv: list[str]) -> int:
    scans = [Path(a) for a in argv] or sorted(LOCAL.glob("*scan*.json"))
    terms = from_machine()
    for scan in scans:
        terms |= from_scan(scan)

    existing = DENYLIST.read_text(encoding="utf-8").splitlines() if DENYLIST.exists() else []
    terms |= {t.strip() for t in existing if t.strip() and not t.startswith("#")}
    terms = {t for t in terms if len(t) >= 3 and t.lower() not in GENERIC_NAMES}

    LOCAL.mkdir(exist_ok=True)
    header = "# Private terms blocked from commits. One per line. Never commit this file.\n"
    DENYLIST.write_text(header + "\n".join(sorted(terms, key=str.lower)) + "\n", encoding="utf-8")
    print(f"local/denylist.txt now holds {len(terms)} terms.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
