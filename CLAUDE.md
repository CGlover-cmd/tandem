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
- Mirroring: whole screen first, then single windows.
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
- Test receivers: Raspberry Pi 3 (shairport-sync, UxPlay). Not set up yet.
- GPU: NVIDIA (NVENC) plus AMD integrated graphics.
- GitHub CLI: if `gh` isn't on PATH yet, use `C:\Program Files\GitHub CLI\gh.exe`. Signed in.
- Windows PowerShell 5.1 quirks: it can't pipe here-strings to `git commit -F -` and adds a BOM
  when piping JSON to `gh api --input -`. Use bash, or write the message to `.git/` first. Git
  also fails on very long temp-file paths.

## Local-only state (not in GitHub, by design)
- `local/discovery-scan.json` and `local/denylist.txt` (private terms for the commit hook).
- The virtualenv and the GitHub sign-in.
- To rebuild on a fresh machine: create the venv, then run
  `python -m pip install pyatv pre-commit detect-secrets==1.5.0`, then `python -m pre_commit install`,
  then a discovery scan into `local/`, then `python tools/build_denylist.py`.

## Conventions
- Python 3.11+, asyncio engine on pyatv, PySide6 + QML UI, ruff + pyright + pytest.
- Engine never imports UI code; UI talks to the engine only through the service API.
- New architecture decisions get an ADR in docs/adr/ (next number, short, Status/Context/Decision/Consequences).
- Model: Opus 5.5 at high effort for all work, coordinator and threads alike (maintainer's choice:
  quality over token cost). Extra-high effort only for the hardest debugging (mirroring encryption,
  multi-output sync); return to high afterwards.
