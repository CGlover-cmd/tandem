"""Rewrite packaging/constraints.txt from the libraries installed in this environment.

Lists every library Tandem needs at run time (`tandem[ui]` and everything it pulls in, for
Windows), pinned to the installed version, under the file's existing header comment. Used by
the monthly dependency check (.github/workflows/dependencies.yml) after the tests pass on the
newest versions. Run it by hand the same way: install, test, then run this.

    python tools/update_constraints.py
"""

from __future__ import annotations

import re
import tomllib
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS = ROOT / "packaging" / "constraints.txt"
ENVIRONMENT: dict[str, str] = {**default_environment(), "sys_platform": "win32"}


def _key(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _wanted(line: str, extras: tuple[str, ...]) -> Requirement | None:
    requirement = Requirement(line)
    marker = requirement.marker
    if marker is not None and not any(
        marker.evaluate({**ENVIRONMENT, "extra": extra}) for extra in ("", *extras)
    ):
        return None
    return requirement


def runtime_closure(extras: tuple[str, ...] = ("ui",)) -> dict[str, str]:
    """Installed name -> version for every run-time dependency of Tandem with `extras`.
    Tandem's own requirements come from pyproject.toml (an editable install's metadata can be
    stale); the rest from the installed libraries."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    lines = list(project["dependencies"])
    for extra in extras:
        lines += project["optional-dependencies"][extra]
    found: dict[str, str] = {}
    pending: list[tuple[str, tuple[str, ...]]] = []
    for line in lines:
        requirement = _wanted(line, ())
        if requirement is not None:
            pending.append((requirement.name, tuple(sorted(requirement.extras))))
    seen: set[tuple[str, tuple[str, ...]]] = set()
    while pending:
        name, wanted = pending.pop()
        if (_key(name), wanted) in seen:
            continue
        seen.add((_key(name), wanted))
        dist = metadata.distribution(name)
        found[dist.metadata["Name"]] = dist.version
        for line in dist.requires or []:
            requirement = _wanted(line, wanted)
            if requirement is None:
                continue
            pending.append((requirement.name, tuple(sorted(requirement.extras))))
    return found


def main() -> None:
    header = [line for line in CONSTRAINTS.read_text(encoding="utf-8").splitlines() if line.startswith("#")]
    pins = sorted(runtime_closure().items(), key=lambda item: _key(item[0]))
    lines = [*header, *(f"{name}=={version}" for name, version in pins)]
    CONSTRAINTS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Pinned {len(pins)} libraries in {CONSTRAINTS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
