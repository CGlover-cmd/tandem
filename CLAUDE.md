# Tandem: project notes for Claude

Open-source Windows AirPlay sender (Apple TV, HomePod, AirPlay 2 speakers), later smart-home
control. Plan and phase status: docs/ROADMAP.md. Decisions: docs/adr/.

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
- Test receivers: Raspberry Pi 3 (shairport-sync, UxPlay).
- GPU: NVIDIA (NVENC) plus AMD integrated graphics.

## Conventions
- Python 3.11+, asyncio engine on pyatv, PySide6 + QML UI, ruff + pyright + pytest.
- Engine never imports UI code; UI talks to the engine only through the service API.
- New architecture decisions get an ADR in docs/adr/ (next number, short, Status/Context/Decision/Consequences).
- Model guidance: Opus/high for protocol, encryption, sync and architecture; Sonnet/medium for UI, tests, packaging and docs.
