"""Block commits that contain private information.

Runs as a pre-commit hook on staged files and on the commit message. See docs/PRIVACY.md.
Usage: python tools/check_private_info.py FILE [FILE ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DENYLIST = REPO_ROOT / "local" / "denylist.txt"

BLOCKED_SUFFIXES = {".pcap", ".pcapng", ".cap", ".har"}

PATTERNS: dict[str, re.Pattern[str]] = {
    "private IP address": re.compile(
        r"\b(?:10(?:\.\d{1,3}){3}"
        r"|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
        r"|192\.168(?:\.\d{1,3}){2}"
        r"|169\.254(?:\.\d{1,3}){2})\b"
    ),
    "MAC address": re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"),
    "email address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "user folder path": re.compile(
        r"(?:\b[A-Za-z]:[\\/]+Users[\\/]+(?!Public\b|Default\b)[A-Za-z0-9._-]+"
        r"|(?<![\w.])/(?:Users|home)/[A-Za-z0-9._-]+)",
        re.IGNORECASE,
    ),
}

# Placeholder values that are safe by design (see "Test data" in docs/PRIVACY.md).
ALLOWED = [
    re.compile(r"^AA[:-]BB[:-]CC[:-]", re.IGNORECASE),  # invented MAC prefix
    re.compile(r"^00(?:[:-]00){5}$"),
    re.compile(r"@users\.noreply\.github\.com$", re.IGNORECASE),
    re.compile(r"^noreply@anthropic\.com$", re.IGNORECASE),
    re.compile(r"@example\.(?:com|org|net)$", re.IGNORECASE),
    re.compile(r"^git@github\.com$", re.IGNORECASE),
]


def load_denylist() -> list[re.Pattern[str]]:
    if not DENYLIST.exists():
        return []
    terms = []
    for line in DENYLIST.read_text(encoding="utf-8").splitlines():
        term = line.strip()
        if term and not term.startswith("#"):
            terms.append(re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE))
    return terms


def is_allowed(value: str) -> bool:
    return any(p.search(value) for p in ALLOWED)


def check_file(path: Path, denylist: list[re.Pattern[str]]) -> list[str]:
    if path.suffix.lower() in BLOCKED_SUFFIXES:
        return [f"{path}: packet captures and HAR files must stay in local/"]
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []  # binary files are covered by detect-secrets and review

    problems = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(line):
                if not is_allowed(match.group(0)):
                    problems.append(f"{path}:{lineno}: {label}")
        for pattern in denylist:
            if pattern.search(line):
                # Never echo the matched term: the output may end up in CI logs.
                problems.append(f"{path}:{lineno}: term from local/denylist.txt")
    return problems


def main(argv: list[str]) -> int:
    denylist = load_denylist()
    problems = []
    for name in argv:
        problems.extend(check_file(Path(name), denylist))
    if problems:
        print("Private information check failed (see docs/PRIVACY.md):")
        print("\n".join(f"  {p}" for p in sorted(set(problems))))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
