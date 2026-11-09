"""Run a spike with the installed Tandem's Python, using this clone's code.

The installed app's pythonw.exe is the program Windows' firewall lets AirPlay speakers reach
on Private networks (ADR-0017); a dev venv's Python isn't. pythonw has no console, so output
goes to local/music-hw/<spike>.out. Usage:
    "C:\\Program Files\\Tandem\\python\\pythonw.exe" spikes/run_under_app.py <spike.py> [args]
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
out_dir = ROOT / "local" / "music-hw"
out_dir.mkdir(parents=True, exist_ok=True)
spike = Path(sys.argv[1])
log = open(out_dir / f"{spike.stem}.out", "w", encoding="utf-8", buffering=1)  # noqa: SIM115
sys.stdout = sys.stderr = log
sys.path.insert(0, str(ROOT / "src"))
sys.argv = [str(spike), *sys.argv[2:]]
runpy.run_path(str(spike), run_name="__main__")
