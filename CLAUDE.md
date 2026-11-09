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
- Phase 10 targets: smart plugs, smart lamps and TV power on/off.
- Music (Phase 6, ADR-0013): Tandem is a remote for Spotify and Apple Music and its router
  carries their sound; it never plays Spotify streams itself (no Web Playback SDK, no
  librespot). Spotify is Web API only, each user brings their own Client ID. Apple Music needs
  the maintainer's MusicKit key, which stays in `local/`.

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
- `.git` is in OneDrive and a crash once zeroed a branch ref and the index. Commit and push work
  in progress before ending any working block. Repair: take the last SHA from
  `.git/logs/refs/heads/<branch>`, write it to the ref, delete `.git/index`, run `git reset`.
- pip must use the Windows certificate store (HTTPS inspection on this machine). pip ≥ 24.2 does
  this by default; on older pip pass `--use-feature=truststore`.
- Windows Smart App Control is ON. It blocks unsigned executables, including pip's console-script
  `.exe` launchers and downloaded toolchains. Always run Python tools as
  `python -m <module>` (e.g. `python -m pre_commit`, `python -m detect_secrets`). Never try to
  disable or bypass it; our own unsigned builds will be blocked too (see ROADMAP risk register).
- Test receivers (retired 2026-10-27: the Pi was reformatted; details kept for a rebuild): Raspberry Pi 3 (Debian 13). UxPlay 1.71 (Spike D) and shairport-sync 5.6 +
  nqptp 1.2.9 built from source in `~/src` (Spike F; Debian's package lacks AirPlay 2), all on
  demand, not at boot; only one at a time (both use port 7000). Use shairport-sync in
  `--service-type=classic`: pyatv's AirPlay 2 sender uses NTP timing, which its AirPlay 2 mode
  rejects. Spike F scripts reach the Pi via the `TANDEM_PI_HOST` env var. SSH key-only login as the `tandem` user
  (private key at `%USERPROFILE%\.ssh\tandem_pi`, outside the project; passwordless sudo set).
- The Apple TV keeps one Companion connection per client: a second Tandem process (CLI, probe
  script, a second window) connecting with the same credentials makes the TV drop the first.
  Close the window before running device scripts, or expect it to reconnect.
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
- Media sessions (Phase 6, `engine/pc_media.py` + `engine/adapters/media_sessions.py`): pywinrt
  `winrt-Windows.Media.Control` (+ Foundation, Foundation.Collections, Storage.Streams; in the
  `ui` extra) loads under Smart App Control and works from the engine's asyncio thread while
  pywebview owns an STA main thread. Events fire on a WinRT thread; hop to asyncio with
  `call_soon_threadsafe`. Browsers re-make their session (same app id, new object) or drop it
  for a moment on a track change, so re-hook on every session event and don't report "nothing
  playing" at once. An app can "accept" a command and do nothing: confirm by the new state.
  Titles, artists and artwork go to the window only (artwork via the token-gated `/artwork`
  route, from memory); never log or print them. `spikes/now_playing_latency.py --page` times
  the bar against Windows' events. A fresh Edge profile auto-opens a sync sign-in dialog and
  holds back media in its hidden tab: don't use Edge for tests; the built-in browser pane works.
- WebView2 here is Evergreen and ships Widevine (software level); PlayReady hardware works only
  outside pywebview's `private_mode`. pywebview handles every new-window request itself (opens
  the system browser), so `window.open` returns null; popups that must talk back need our own
  `NewWindowRequested` handling (Music spike 2).
- GitHub CLI: if `gh` isn't on PATH yet, use `C:\Program Files\GitHub CLI\gh.exe`. Signed in.
- Windows PowerShell 5.1 quirks: it can't pipe here-strings to `git commit -F -` and adds a BOM
  when piping JSON to `gh api --input -`. Use bash, or write the message to `.git/` first. Git
  also fails on very long temp-file paths.
- Bash-tool heredocs here turn `\\` into `\`, which silently breaks regexes and Windows paths.
  Write source files with the Write tool, not `cat <<EOF`.
- pyright doesn't find the venv on its own: run
  `python -m pyright --pythonpath <venv python.exe>` (CI does the same).
- Smart App Control started blocking zeroconf's compiled `_cache.pyd` (2026-10-27). Reinstall it
  as pure Python: `SKIP_CYTHON=1 python -m pip install --force-reinstall --no-deps --no-binary
  zeroconf zeroconf==<version>`. Any upgrade that pulls a zeroconf wheel brings the block back.
- Our own installer can't run here (unsigned, Smart App Control). Build the app folder outside
  OneDrive (`%USERPROFILE%\.tandem-build`) with `packaging/build_bundle.py`: its python.exe is
  python.org's signed one, so `--smoke` and opening the window work locally. The installer is
  built, installed and tested in CI only (`.github/workflows/release.yml`).
- HAP-python (Home bridge) uses TCP 51827 and prints the setup code to stdout unless the
  Bridge's `setup_message` is overridden (it is). Its state file is
  `%LOCALAPPDATA%\Tandem\home-bridge.state`, DPAPI-encrypted.
- Firewall (ADR-0017, 1.1.1): allowed from the local subnet on Private/Domain networks, blocked on
  Public; `tandem.ui.network_trust` reads the category (no admin) and the window offers to mark
  the network Private. This PC's Wi-Fi is Public, so the installed app shows that note.
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
- Typed commands (Phase 10a, ADR-0014): parser in `engine/commands.py`, dispatcher in
  `engine/command_dispatch.py` behind a small `CommandServices` protocol (`EngineCommandServices`,
  which the demo uses too). Results are codes plus params; the words
  live in `web/src/strings.ts`. Command text and results name devices: never log them. Never
  call the feature "Siri".
- Anything the engine logs or shows goes through `Redactor`; register new private values
  (names, ids) with it. The developer tool (`python -m tandem`) prints placeholders unless
  `--show-private` is given; Claude never passes that flag.
- The UI's side of the engine's API is the `Backend` protocol in `src/tandem/ui/backend.py`
  (ADR-0008). `tandem.bridge.EngineBackend` implements it and is the only module that imports
  both layers. The demo (`--demo`, screenshots, the window's tests) is the same bridge and engine
  on invented devices (ADR-0019): `tandem.engine.adapters.demo.DemoDevices` plugs in at the
  engine's device seam and `tandem.bridge.DemoBackend` is `EngineBackend` over it, so a feature is
  written once. Window tests use `tests/ui/demo_harness.py` (`settle()` after each command: the
  engine works through events). Which services an Apple TV must pair, in order, is
  `engine.pairing.services_to_pair` (used by the window and the developer tool).
- Errors for the window are codes: `BackendError(Problem.X)` (`tandem.ui.backend.Problem`), with
  the words in `problems` in `web/src/strings.ts`. Control errors are classified once by
  `engine.control.failure_of`; play/pause intents are `DeviceControls.play()/pause()/play_pause()`.
- Python here is the Microsoft Store build, which redirects `%LOCALAPPDATA%` writes to its own
  package folder (`%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.11_*\LocalCache\Local`).
  So `%LOCALAPPDATA%\Tandem` looks empty from outside Python, though Tandem's files are there.
- UI logic stays in Python (`tandem.ui.controller`, tested with pytest); React only renders the
  state it's sent and sends commands back over the loopback WebSocket (`tandem.ui.server`). Keep
  `web/src/types.ts` in step with `AppController.snapshot()` and its commands, then run
  `python tools/write_contract.py`: it writes `web/src/contract.generated.ts`, which the web type
  check holds against types.ts (a pytest test fails while it's stale). Commands are registered
  per panel in a `CommandTable` (`tandem.ui.window_commands`). User-facing words live in
  `web/src/strings.ts`; Python sends codes, not sentences.
- Every colour is in `web/src/theme.ts`; `theme.test.ts` checks WCAG AA contrast on every
  background. Window backgrounds are listed in both `theme.ts` and `tandem.ui.backend.BACKGROUNDS`
  (a test keeps them equal).
- Check visuals by running `python -m tandem.ui --demo --no-window` (invented devices, so screenshots are
  safe to share) and opening the printed address in the built-in browser. Never log that address:
  it carries the launch token. Stop the server by its own PID, never by image name.
  Without `--demo` the window shows real device names, so never screenshot it; check it through
  the WebSocket and print kinds and states only.
- The front-end build goes to `src/tandem/ui/static/` (git-ignored, shipped in the wheel).
- Panels added after ADR-0008 keep their bridge code in their own modules, mixed into
  `EngineBackend`: `tandem.bridge_audio` (Audio, Send), `tandem.bridge_home` (Home bridge) and
  `tandem.bridge_library` (music library, radio, queue, Apple catalog), with the controller
  side in `ui/audio_panel.py` and `ui/library_panel.py`. The demo's invented music is
  `engine/adapters/demo_music.py`, fed to the real library, radio and catalog (ADR-0019).
  Audio outputs are owned by the engine (`engine/outputs.py`, `engine.outputs`: saved
  settings, states, groups, restore, line-up); switch outputs there, never with
  `Engine.start_output` directly (ADR-0019).
- Groups and line-up (ADR-0018): groups in `engine/output_groups.py` (switched by
  `engine.outputs`); line-up in `engine/lineup.py` + `AudioHub.probe` + `adapters/microphone.py`.
  The microphone on this PC refuses desktop apps right now (miniaudio init -6, access denied),
  so a hardware line-up check needs the maintainer to allow it in Windows' privacy settings.
  Open the mic off the event loop (`asyncio.to_thread`): opening it can block.
- `tools/update_constraints.py` rewrites `packaging/constraints.txt` from the installed set; the
  monthly `dependencies.yml` workflow runs it after the tests pass on the newest versions.
- Music library and radio (Phase 6): `engine/library.py` (folders, tags cached in
  `library.json`, albums) and `engine/radio.py` (Radio Browser search, saved stations in
  `radio.json`), with file and HTTP access in `adapters/library_files.py` (tinytag) and
  `adapters/radio_browser.py`. The state sends albums without their songs; an album's songs and
  a song search go only while the page shows them, so state messages stay small. miniaudio's
  stream generator returns the first chunk when primed: keep it (`adapters/decoders.py`), or
  every track loses its first 23 ms.
- Apple Music catalog search (ADR-0013, 2026-11-08 note): `engine/apple_catalog.py` with HTTP
  and `music://` opening in `adapters/itunes_catalog.py`. Apple's artwork and badge pass
  through Tandem's server (`/catalog-art`, `/apple-music-badge`, sandboxing CSP), are fetched
  at run time and stay in memory: never commit or save them. No previews. Keep the 20-a-minute
  limit. Don't open a real song link without the maintainer's OK (it plays from their account).
  A song link opens its album page in the Apple Music app and doesn't start it (checked
  2026-11-09): keep the button "Open", not "Play".
- Library versions: `packaging/constraints.txt` pins every runtime library; the app folder, the
  release workflow and CI install with `-c` it. Move a pin only on purpose, after the tests and
  a hardware check (1.0.0 shipped an unpinned srptools 2.0 that broke all Apple handshakes).
- Packaging (ADR-0017): `packaging/build_bundle.py` (embeddable Python app folder) and
  `packaging/tandem.iss` (Inno Setup). The version lives in `pyproject.toml` and
  `tandem/__init__.py`; release notes in `docs/release-notes.md`. Pushing a `v*` tag publishes a
  GitHub pre-release: only with the maintainer's OK.
- Don't prune `webview/lib/runtimes` from the app folder: pywebview's WinForms back end looks up
  every architecture's folder at import, and 1.2.0's window never opened without them. The
  smoke check's demo runs without a window, so it imports `webview.platforms.winforms` itself.
- Setup closes a running Tandem (ADR-0017, 1.2.1 addendum): it sets the `Local\TandemQuit`
  event, which `tandem.ui.platform.on_quit_request` waits on, then stops any Python still
  running from the install folder, and reopens Tandem if its window was open. The event and
  mutex names live in both `platform.py` and `tandem.iss`; a test keeps them equal. Running a
  dev copy while setup runs: it gets asked to quit too.
- HeroUI sizes every svg inside a `Button` with a class (14 px here); our icons set their size
  inline so it wins. HeroUI's `.modal__body` is muted by default; `index.css` resets it to the
  primary colour. WebView2 draws arrow scrollbars unless `scrollbar-width`/`-color` stay at
  `auto` and `::-webkit-scrollbar` is styled (it is, in `index.css`).
- HeroUI's `Switch` renders its input only inside `Switch.Content`: put `Switch.Control` (and a
  label, or an `sr-only` span) inside it, or the switch has no accessible control.
- Online lookups (docs/privacy-policy.md): app icons (itunes.apple.com) and the update check
  (api.github.com), both on by default, both offered on the installer's Privacy page. Any new
  request that leaves the PC must be added to that policy and get an off switch; SignPath
  Foundation's terms require it. `python -m tandem privacy --app-icons off` is how the installer
  writes the choice.
- New architecture decisions get an ADR in docs/adr/ (next number, short, Status/Context/Decision/Consequences).
- Model: Opus 5.5 at high effort for all work, coordinator and threads alike (maintainer's choice:
  quality over token cost). When a task would fail or be very inefficient at high (mirroring
  encryption, multi-output sync, a bug that survives two attempts), switch to extra-high, then back
  to high once it's solved. A coordinator does this itself for threads it started
  (`set_session_effort`; the app asks the maintainer to approve the raise). No session can change
  its own effort, so for itself it recommends the switch to the maintainer, with a one-line reason.
