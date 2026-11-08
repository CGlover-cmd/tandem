"""Build Tandem's app folder for the installer (Phase 9, ADR-0017). Runs in CI on Windows.

The folder holds Python's official embeddable runtime (python.org's signed python.exe and
pythonw.exe), Tandem's wheel and its libraries, and the icon. No freezer is used: a frozen
.exe would be one more unsigned program for SmartScreen and Smart App Control to stop.

Usage (from the repo root, after building the front end and the wheel):
    python packaging/build_bundle.py --wheel dist/tandem-1.0.0-py3-none-any.whl --out build/Tandem
    python packaging/build_bundle.py --smoke build/Tandem
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

EMBED_URL = "https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip"
ROOT = Path(__file__).resolve().parents[1]
# The tested library versions: a new dependency release can't slip into a build.
CONSTRAINTS = ROOT / "packaging" / "constraints.txt"


def build(wheel: Path, out: Path, python_version: str) -> None:
    if out.exists():
        shutil.rmtree(out)
    runtime = out / "python"
    runtime.mkdir(parents=True)

    archive = out.parent / f"python-{python_version}-embed-amd64.zip"
    if not archive.exists():
        print(f"Downloading the embeddable Python {python_version}")
        urllib.request.urlretrieve(EMBED_URL.format(v=python_version), archive)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(runtime)

    # The ._pth file decides sys.path for the embedded runtime: add site-packages, and
    # `import site` so .pth files work (pywin32-style packages rely on them).
    pth = next(runtime.glob("python3*._pth"))
    zip_name = next(runtime.glob("python3*.zip")).name
    pth.write_text(f"{zip_name}\n.\nLib\\site-packages\nimport site\n", encoding="ascii")

    site_packages = runtime / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    pip = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-warn-script-location",
        "-c",
        str(CONSTRAINTS),
        "--target",
    ]
    # zeroconf as pure Python: its compiled modules are blocked by Smart App Control on some
    # PCs (docs/ROADMAP.md risk register). The pure version is the same code.
    env = dict(os.environ, SKIP_CYTHON="1")
    subprocess.run(
        [*pip, str(site_packages), "--no-binary", "zeroconf", "zeroconf"], check=True, env=env
    )
    subprocess.run([*pip, str(site_packages), f"{wheel}[ui]"], check=True, env=env)
    for junk in site_packages.glob("*/__pycache__"):
        shutil.rmtree(junk, ignore_errors=True)
    shutil.rmtree(site_packages / "bin", ignore_errors=True)

    from tandem.ui.icon import write_ico

    write_ico(out / "Tandem.ico")
    shutil.copy(ROOT / "LICENSE", out / "LICENSE.txt")
    shutil.copy(ROOT / "README.md", out / "README.md")
    print(f"Built {out}")


def smoke(out: Path) -> None:
    """Start the bundled app with demo devices and check it serves its window's page."""
    python = out / "python" / "python.exe"
    imports = (
        "import tandem, tandem.ui.app, tandem.bridge, tandem.engine.adapters.pyatv_adapter, "
        "tandem.engine.adapters.hap_bridge, webview, pystray, miniaudio, pyhap, aiohttp; "
        "import winrt.windows.media.control; print(tandem.__version__)"
    )
    subprocess.run([str(python), "-c", imports], check=True)
    subprocess.run([str(python), "-m", "tandem", "--help"], check=True, stdout=subprocess.DEVNULL)

    process = subprocess.Popen(
        [str(python), "-m", "tandem.ui", "--demo", "--no-window"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        assert process.stdout is not None
        deadline = time.monotonic() + 60
        url = None
        while time.monotonic() < deadline and url is None:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            match = re.search(r"Open (http://127\.0\.0\.1:\d+/\?token=\S+)", line)
            if match:
                url = match.group(1)
        if url is None:
            raise SystemExit("The bundled app didn't start its server")
        with urllib.request.urlopen(url, timeout=10) as response:
            page = response.read().decode("utf-8", errors="replace")
        if response.status != 200 or '<div id="root"' not in page:
            raise SystemExit("The bundled app's page didn't load")
        print("Smoke test passed: the bundled app starts and serves its window")
    finally:
        process.terminate()
        process.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "Tandem")
    parser.add_argument("--python-version", default="3.11.9")
    parser.add_argument("--smoke", type=Path, help="smoke-test an existing bundle")
    args = parser.parse_args()
    if args.smoke:
        smoke(args.smoke)
        return
    if args.wheel is None:
        parser.error("--wheel is required to build")
    build(args.wheel.resolve(), args.out.resolve(), args.python_version)


if __name__ == "__main__":
    main()
