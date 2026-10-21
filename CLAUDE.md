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
- Test receivers: Raspberry Pi 3 (Debian 13). UxPlay 1.71 (Spike D) and shairport-sync 5.6 +
  nqptp 1.2.9 built from source in `~/src` (Spike F; Debian's package lacks AirPlay 2), all on
  demand, not at boot; only one at a time (both use port 7000). Use shairport-sync in
  `--service-type=classic`: pyatv's AirPlay 2 sender uses NTP timing, which its AirPlay 2 mode
  rejects. Spike F scripts reach the Pi via the `TANDEM_PI_HOST` env var. SSH key-only login as the `tandem` user
  (private key at `%USERPROFILE%\.ssh\tandem_pi`, outside the project; passwordless sudo set).
- Spike scripts live in `spikes/` (throwaway; pick devices by model, never print names, addresses
  or identifiers). For PIN pairing, run the script in the background and write the PIN the
  maintainer reads off the TV to `local/spike-a/pin.txt`. pyatv keys are in `local/spike-a/`.
- Hardware checks with the developer tool: set `TANDEM_HOME` to a folder under `local/` so test
  credentials stay out of the real app's `%LOCALAPPDATA%\Tandem`. Pair in the background with
  `python -m tandem pair apple_tv --pin-file local/<folder>/pin.txt` and write each PIN the
  maintainer reads off the TV to that file. Target only the reference devices (by kind or model),
  never `all`: the network has other AirPlay devices that are excluded from testing.
- Apple TV pairing takes two PINs: remote control (Companion), then AirPlay. pyatv also lists
  AirPlay audio (RAOP) as needing pairing, but the TV never shows a PIN for it, so `pair` skips
  it unless asked. A Companion attempt can be rejected once; retrying with a fresh PIN worked.
- The reference Apple TV's Volume Control is "Auto via IR (TV)": the Siri Remote sets the TV's
  volume by infrared, so Tandem reports no volume control for it (ADR-0009). Media titles from
  now-playing are personal: the developer tool hides them; Claude never passes `--show-private`.
- GPU: NVIDIA (NVENC) plus AMD integrated graphics. The built-in 4K 60 Hz display runs on the
  NVIDIA GPU, so desktop duplication captures there (Spike E). AMF is slow on this laptop.
- Video spike tooling (Spike E): PyAV (bundled FFmpeg, NVENC/AMF/MF/x264) and dxcam. Use
  `VideoFrame.from_numpy_buffer`, not `from_ndarray` (36 ms per 4K frame). dxcam 0.3.0 crashes in
  `release()`/COM cleanup, so spikes end with `os._exit`. PyAV can't pass D3D11 GPU frames to an
  encoder (no hw_frames_ctx), so a zero-copy capture-to-NVENC path needs native code.
- Audio capture: miniaudio (a pyatv dependency) does WASAPI loopback; its Python wrapper lacks a
  loopback class, so open `ma_device_type_loopback` via `_miniaudio.lib` (see `spikes/spike_c_loopback.py`).
  On this laptop loopback follows the Windows volume and mute (Spike C). Loopback delivers
  nothing at all while nothing plays (Phase 4), so the audio pipeline fills silence itself.
- The test Pi answers at its mDNS name (`<host>.local`); the maintainer's spike scripts read it
  from `TANDEM_PI_HOST`. The Phase 4 Pi check needs numpy in the venv.
- Front end (ADR-0010): Node 24 and npm are installed. Smart App Control can block a native npm
  binary until it has reputation ("An Application Control policy has blocked this file"):
  rolldown 1.2.15 was blocked, so `web/package.json` pins `rolldown` 1.2.14 via `overrides`.
  If a build breaks that way after an upgrade, pin the last version that loads. TypeScript 7
  (`tsc`), Tailwind's oxide and lightningcss load fine.
- pywebview runs WebView2 through pythonnet; its window must own the main thread, so
  `tandem.ui.app` runs asyncio on a second thread and pystray on a third.
- A second clone of the repo needs its own venv: the shared `tandem-dev` venv has an editable
  install pointing at the OneDrive checkout, so tests in another clone would import that copy.
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
- To rebuild on a fresh machine: create the venv, then run `python -m pip install -e ".[dev,ui]"`
  from the repo root (plus `av dxcam numpy` for the Spike E script), then
  `python -m pre_commit install`,
  then a discovery scan into `local/`, then `python tools/build_denylist.py`.

## Conventions
- Python 3.11+, asyncio engine on pyatv, ruff + pyright + pytest. UI: React 19 + HeroUI 3 +
  Tailwind 4 (TypeScript, Vite, Vitest) in `web/`, shown in a WebView2 window (ADR-0010).
- Engine never imports UI code; UI talks to the engine only through the service API.
- Package code is in `src/tandem/` (ADR-0007). Only `engine/adapters/` imports pyatv; core
  modules take a scanner or connector callable so tests use fakes. Tests live in `tests/`, with
  shared fakes in `tests/conftest.py`; keep engine coverage ≥80% (CI enforces it).
- Anything the engine logs or shows goes through `Redactor`; register new private values
  (names, ids) with it. The developer tool (`python -m tandem`) prints placeholders unless
  `--show-private` is given; Claude never passes that flag.
- The UI's side of the engine's API is the `Backend` protocol in `src/tandem/ui/backend.py`
  (ADR-0008); `DemoBackend` (invented devices) stands in until the engine adapter for it exists.
- UI logic stays in Python (`tandem.ui.controller`, tested with pytest); React only renders the
  state it's sent and sends commands back over the loopback WebSocket (`tandem.ui.server`). Keep
  `web/src/types.ts` in step with `AppController.snapshot()` and `handle()`. User-facing words
  live in `web/src/strings.ts`; Python sends codes, not sentences.
- Every colour is in `web/src/theme.ts`; `theme.test.ts` checks WCAG AA contrast on every
  background. Window backgrounds are listed in both `theme.ts` and `tandem.ui.backend.BACKGROUNDS`
  (a test keeps them equal).
- Check visuals by running `python -m tandem.ui --no-window` (demo devices only, so screenshots are
  safe to share) and opening the printed address in the built-in browser. Never log that address:
  it carries the launch token. Stop the server by its own PID, never by image name.
- The front-end build goes to `src/tandem/ui/static/` (git-ignored, shipped in the wheel).
- New architecture decisions get an ADR in docs/adr/ (next number, short, Status/Context/Decision/Consequences).
- Model: Opus 5.5 at high effort for all work, coordinator and threads alike (maintainer's choice:
  quality over token cost). When a task would fail or be very inefficient at high (mirroring
  encryption, multi-output sync, a bug that survives two attempts), switch to extra-high, then back
  to high once it's solved. A coordinator does this itself for threads it started
  (`set_session_effort`; the app asks the maintainer to approve the raise). No session can change
  its own effort, so for itself it recommends the switch to the maintainer, with a one-line reason.
