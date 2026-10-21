# Tandem: project notes for Claude

Open-source Windows AirPlay sender (Apple TV, HomePod, AirPlay 2 speakers), later smart-home
control. Plan, scope and phase status: docs/ROADMAP.md. Decisions: docs/adr/.
Public repo: https://github.com/CGlover-cmd/tandem (branch `main`).

## Session routine
- **Start:** read "Status and next step" in docs/ROADMAP.md and continue from there.
- **During:** keep the docs in step with the work, in the same commit as the change:
  - README.md: whenever status, features, install or usage steps change.
  - CLAUDE.md: whenever a new decision, convention, environment fact or tooling gotcha appears.
  - docs/adr/: whenever an architecture decision is made or changed.
- **End** (also when the maintainer says "wrap up"): update "Status and next step" and the phase
  checkboxes in docs/ROADMAP.md, check README and CLAUDE.md are current, then commit and push,
  so the next session can pick up from the repo alone.

## Maintainer decisions (from planning)
- Apple-inspired look: rounded corners, translucency, smooth animation.
- Audio outputs: any mix of AirPlay devices and the PC's own speakers. A virtual audio driver
  install is acceptable if needed (ADR-0005).
- Mirroring: shelved. Spike D found it is FairPlay-gated with no legitimate open-source sender;
  we will not reverse-engineer or bypass FairPlay in a public project (ADR-0006).
- The shipped app needs no extra devices. It talks straight from Windows to the AirPlay
  receivers. The Raspberry Pi (UxPlay / shairport-sync) is a test tool only, never a dependency
  users install.
- Support Windows 10 22H2+ as well as Windows 11. No Chromecast.
- Build order follows dependencies and risk, not feature preference.
- No timelines or duration estimates in the docs.
- Test only on the reference devices in ROADMAP; other AirPlay devices on the network are excluded.
- Phase 9 targets: smart plugs, smart lamps and TV power on/off.

## Non-negotiable: privacy first
The GitHub repo is PUBLIC. Follow docs/PRIVACY.md without exception:
- Private data (scans, logs, captures, credentials, device names, addresses, identifiers) goes
  only in git-ignored `local/`. Never quote it in committed files, commit messages, PRs or issues.
- Fixtures and examples use invented values (192.0.2.x, AA:BB:CC:..., "Living Room Speaker").
- Device models (e.g. a soundbar's model number) aren't personal data; tools may print them.
- Never bypass pre-commit hooks (`--no-verify`). If a hook blocks a commit, fix the content.
- Commit email must be the GitHub noreply address (set per-repo).

## Roles
The maintainer tests on real hardware; Claude writes the code. Ask the maintainer for physical
steps (reading PINs off the TV, confirming audio, changing Home app settings).

## Environment
- Dev virtualenv lives OUTSIDE the OneDrive-synced project: `%USERPROFILE%\.venvs\tandem-dev`
  (Python 3.11). Run tools via `%USERPROFILE%\.venvs\tandem-dev\Scripts\python.exe`.
- pip must use the Windows certificate store (HTTPS inspection on this machine). pip ≥ 24.2 does
  this by default; on older pip pass `--use-feature=truststore`.
- Windows Smart App Control is ON. It blocks unsigned executables, including pip's console-script
  `.exe` launchers and downloaded toolchains. Always run Python tools as
  `python -m <module>` (e.g. `python -m pre_commit`, `python -m detect_secrets`). Never try to
  disable or bypass it; our own unsigned builds will be blocked too (see ROADMAP risk register).
- Test receivers: Raspberry Pi 3. UxPlay 1.71 is installed (Spike D) and runs on demand;
  shairport-sync for Spike F not installed yet. SSH key-only login as the `tandem` user
  (private key at `%USERPROFILE%\.ssh\tandem_pi`, outside the project; passwordless sudo set).
- Spike scripts live in `spikes/` (throwaway; pick devices by model, never print names, addresses
  or identifiers). For PIN pairing, run the script in the background and write the PIN the
  maintainer reads off the TV to `local/spike-a/pin.txt`. pyatv keys are in `local/spike-a/`.
- GPU: NVIDIA (NVENC) plus AMD integrated graphics. The built-in 4K 60 Hz display runs on the
  NVIDIA GPU, so desktop duplication captures there (Spike E). AMF is slow on this laptop.
- Video spike tooling (Spike E): PyAV (bundled FFmpeg, NVENC/AMF/MF/x264) and dxcam. Use
  `VideoFrame.from_numpy_buffer`, not `from_ndarray` (36 ms per 4K frame). dxcam 0.3.0 crashes in
  `release()`/COM cleanup, so spikes end with `os._exit`. PyAV can't pass D3D11 GPU frames to an
  encoder (no hw_frames_ctx), so a zero-copy capture-to-NVENC path needs native code.
- Audio capture: miniaudio (a pyatv dependency) does WASAPI loopback; its Python wrapper lacks a
  loopback class, so open `ma_device_type_loopback` via `_miniaudio.lib` (see `spikes/spike_c_loopback.py`).
  On this laptop loopback follows the Windows volume and mute (Spike C).
- GitHub CLI: if `gh` isn't on PATH yet, use `C:\Program Files\GitHub CLI\gh.exe`. Signed in.
- Windows PowerShell 5.1 quirks: it can't pipe here-strings to `git commit -F -` and adds a BOM
  when piping JSON to `gh api --input -`. Use bash, or write the message to `.git/` first. Git
  also fails on very long temp-file paths.
- Bash-tool heredocs here turn `\\` into `\`, which silently breaks regexes and Windows paths.
  Write source files with the Write tool, not `cat <<EOF`.
- pyright doesn't find the venv on its own: run
  `python -m pyright --pythonpath <venv python.exe>` (CI does the same).
- `local/denylist.txt` holds real room and device names, so even an invented test name can clash
  with it. If the privacy hook flags a test value, pick another invented one.

## Local-only state (not in GitHub, by design)
- `local/discovery-scan.json` and `local/denylist.txt` (private terms for the commit hook).
- The virtualenv and the GitHub sign-in.
- To rebuild on a fresh machine: create the venv, then run `python -m pip install -e ".[dev]"`
  from the repo root (plus `av dxcam numpy` for the Spike E script), then
  `python -m pre_commit install`,
  then a discovery scan into `local/`, then `python tools/build_denylist.py`.

## Conventions
- Python 3.11+, asyncio engine on pyatv, PySide6 + QML UI, ruff + pyright + pytest.
- Engine never imports UI code; UI talks to the engine only through the service API.
- Package code is in `src/tandem/` (ADR-0007). Only `engine/adapters/` imports pyatv; core
  modules take a scanner or connector callable so tests use fakes. Tests live in `tests/`, with
  shared fakes in `tests/conftest.py`; keep engine coverage ≥80% (CI enforces it).
- Anything the engine logs or shows goes through `Redactor`; register new private values
  (names, ids) with it. The developer tool (`python -m tandem`) prints placeholders unless
  `--show-private` is given; Claude never passes that flag.
- New architecture decisions get an ADR in docs/adr/ (next number, short, Status/Context/Decision/Consequences).
- Model: Opus 5.5 at high effort for all work, coordinator and threads alike (maintainer's choice:
  quality over token cost). When a task would fail or be very inefficient at high (mirroring
  encryption, multi-output sync, a bug that survives two attempts), switch to extra-high, then back
  to high once it's solved. A coordinator does this itself for threads it started
  (`set_session_effort`; the app asks the maintainer to approve the raise). No session can change
  its own effort, so for itself it recommends the switch to the maintainer, with a one-line reason.
