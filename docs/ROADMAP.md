# Tandem roadmap

An open-source Windows app that sends audio and video to AirPlay devices
(Apple TV, HomePod, AirPlay 2 speakers and TVs), with a polished Apple-inspired interface.
(Screen mirroring was investigated and shelved: it is FairPlay-gated with no legitimate
open-source path — see ADR-0006.) Smart-home control and typed commands follow (Phase 10);
Tandem can't call Siri, but Siri on a HomePod can drive Tandem through the Home app
(ADR-0014).

> Name: **Tandem**. Names and branding must not use Apple trademarks (AirPlay, Apple, HomePod,
> HomeKit). We describe compatibility in plain words, e.g. "works with Apple TV and HomePod".

## Status and next step

_Update this section at the end of every working session._

- **1.2.1 (2026-11-09), a pre-release: fixes 1.2.0's install.** It carries the three entries
  below.
- **1.2.0's window doesn't open (2026-11-09, fixed in 1.2.1):** the app folder left out
  pywebview's x86 and ARM64 WebView2 folders, which it looks up at start, so the window failed
  and the tray thread kept a windowless Tandem holding the single-instance lock. The folders
  are kept, the smoke check imports the window's back end, and a failed window now says so
  and exits.
- **Installer closes Tandem (2026-11-09, in 1.2.1):** installing 1.2.0 over a running
  copy hit Windows' "unable to automatically close all applications" prompt. Setup now asks
  Tandem to quit, stops older copies run from its folder, and reopens it afterwards; the
  uninstaller closes it too (ADR-0017, 1.2.1 addendum). Checked in CI's installer job.
- **Architecture and UI review (2026-11-08, in 1.2.1):** the review's 14
  recommendations are on their own branch, on top of 1.2.0
  ([ADR-0019](adr/0019-one-bridge-demo-on-the-engine.md)). The demo runs on the real engine
  through a demo device adapter (the old demo backend is gone), audio outputs live in the
  engine, play/pause and control errors are handled once, the bridge sends problem codes, and
  `tools/write_contract.py` keeps `types.ts` checked against Python. Window polish: icons at
  their real size, primary-colour row titles in sheets, card actions that wrap, quiet
  scrollbars and sliders, a remote that fits without scrolling, one close per sheet. Nothing
  here changes what talks to devices, but it should ride along with the next hardware retest.
- **Current state (2026-11-06): 1.1.0, a pre-release, fixes the maintainer's 1.0.0 test.**
  The 1.0.0 installer shipped srptools 2.0, which broke every Apple handshake (pairing showed
  "wrong PIN"; HomePods and the soundbar failed). Library versions are now pinned
  (`packaging/constraints.txt`, ADR-0017 addendum) and audio to a HomePod mini and the soundbar
  was checked from a locally built app folder. Also in 1.1.0: instant feedback on the Audio
  panel's switches, Windows' own output shown as on, one source (ADR-0015 addendum), Advanced
  settings (delays, app icons, Home bridge), a Pair button in Getting started, Sky as the
  default background and a photo background.
- **1.2.0 (2026-11-08):** the maintainer's ideas list after the 1.0 test: automatic line-up
  with the microphone and speaker groups (ADR-0018), an All speakers slider, remembered
  speakers, tray speaker switches, Ctrl+Alt+K from anywhere, clearer speaker errors, update
  check and Report a problem, photo blur, compile-on-install and a smaller app folder, idle
  scanning, a monthly dependency check and a SignPath signing hook (docs/signing.md). All
  untested on hardware; the release notes list the checks.
- **1.1.1 (2026-11-08):** Windows' Private/Public setting is Tandem's per-network trust list:
  allowed (local subnet) on Private, blocked on Public, so Windows no longer asks "allow
  Python?"; on a Public network the window offers to mark it Private (maintainer's choice;
  ADR-0017 addendum). The maintainer's own Wi-Fi is currently Public, so expect the note.
- **1.0.0 (2026-11-04)** was built as a pre-release. Every phase except the
  shelved mirroring (8) and the optional smart-home steps 10c–10d is built and covered by tests,
  and CI builds, installs and smoke-tests the Windows installer
  ([ADR-0017](adr/0017-installer-embedded-python.md)). The maintainer handed the finish to
  Claude without hands-on tests, so the hardware checks still open are listed in
  [release-notes.md](release-notes.md). Built since the last hardware session: the Audio panel
  (AirPlay and PC outputs with volume and delay, source choice; ADR-0015), Send to TV (file
  picker or link), the Music tab and now-playing bar, command-bar audio, the Getting started
  checklist, the Home bridge (ADR-0016), one window per user, and the installer.
- **Next:** the maintainer installs 1.1.1 and reruns the release notes' checklist (pairing
  first); then the HomePod mini's ~5 s lag (needed for the Phase 5 sync exit), code
  signing (SignPath), and 10c voice input.
- **Repo note:** 1.0.0 was PR #12, 1.1.0 was PR #16 (both merged). The Raspberry Pi test receiver was retired on
  2026-10-27, so classic-AirPlay checks need a new receiver if they're wanted again.
- **Done:** dev environment, device discovery (all reference devices found), privacy guardrails,
  public repo with GitHub secret scanning and push protection. Spike A passed: pairing, remote
  keys, power and now-playing all work on the Apple TV ([findings](spikes/spike-a-apple-tv.md)).
  Spike B passed: a test tone streamed cleanly to the soundbar and both HomePod minis, with no
  pairing ([findings](spikes/spike-b-audio.md)). Spike C passed: WASAPI loopback captures the
  PC's audio with no gaps at low CPU, but follows the Windows volume and mute; ADR-0005 accepted
  (loopback by default, optional user-installed virtual audio device)
  ([findings](spikes/spike-c-loopback.md)). Spike D ran: screen mirroring is a **no-go** for
  now. Receivers accept it, but there is no open-source way to send it (pyatv has no mirroring
  sender) and the video is keyed by FairPlay; we will not reverse-engineer or bypass FairPlay in
  a public project. Phase 8 is shelved; everything else is FairPlay-free and on track. ADR-0006
  accepted ([findings](spikes/spike-d-mirroring.md)). Spike E passed for 1080p: capture, NVENC
  encode and decode back take about 60 ms on the PC, and 1080p30 runs at full rate from Python.
  4K60 would need frames to stay on the GPU (a native helper), which only matters if mirroring
  reopens ([findings](spikes/spike-e-encode.md)). Spike F passed in classic AirPlay mode:
  shairport-sync on the Pi receives pyatv's stream bit-exact (2 minutes, no gaps), so audio can
  be checked automatically. pyatv's AirPlay 2 sender uses NTP timing, which shairport-sync's
  AirPlay 2 mode doesn't accept, so the AirPlay 2 path stays a hardware check
  ([findings](spikes/spike-f-pi-receiver.md)).
- **Phase 1 done:** the engine core is built (ADR-0007). The developer tool discovered, paired,
  connected to and disconnected from every reference device: the Apple TV (remote control and
  AirPlay PINs), both HomePod minis and the soundbar (no pairing needed).
  `python -m tandem diagnose` writes a redacted diagnostics bundle.
- **Phase 3 so far (engine):** the control API is built (ADR-0009) and checked live on the
  Apple TV: remote keys move the selection, play and pause work, now-playing follows, and
  the play controls appear once a video plays. Volume reports none on the reference setup
  (the TV's volume is set by IR from the Siri Remote).
- **Phase 3 UI:** a Remote sheet on connected devices: a round touch pad (tap or hold; also
  arrow keys, Enter and Backspace), Back, Home and play/pause, a now-playing card with
  progress and the media buttons the device offers, power, and volume as a slider, steps or
  a note to use the TV remote. Built and checked with demo devices.
- **Phase 3 UI, apps and typing:** the Remote sheet has **Apps** (the TV's apps as tiles, with
  a search box; picking one opens it) and **Keyboard** (types into the TV's text field, sending
  the newest text a moment after each keystroke). The engine now pushes keyboard focus, so the
  keyboard opens by itself when the TV asks for text. Built and checked with demo devices.
- **Hardware check, Apps and Keyboard:** the keyboard field opened on the Apple TV, but the
  maintainer saw no typed text on the TV. Re-tested from the PC: text typed through the app's
  own path reached the TV's search box, so the miss wasn't reproduced. Typing with no text
  field selected was silently dropped by pyatv; Tandem now says so instead. Apps now show real
  icons from the App Store lookup, with drawn icons for built-in apps and a Settings switch
  ([ADR-0012](adr/0012-app-icons-from-the-app-store.md)).
- **Hardware check, Keyboard retry:** typing into the Apple TV's search box from the window
  works in real time.
- **Phase 10a (typed command bar), built:** Ctrl+K (or **Commands** in the header) opens a
  command bar. It understands play, pause, next, previous, volume (level or up/down), open an
  app on the TV, and turn a device on or off, with device names matched loosely; it says what
  Enter will do as you type and asks "which device?" when it can't tell. "Send audio" and
  "stop streaming" answer "not available yet" until Phase 4 lands. No Siri: see
  [ADR-0014](adr/0014-commands-no-siri.md). Checked in the demo window; the hardware gate (20
  sample commands on the real devices) is still to run.
- **In parallel, Phase 2 UI shell (started):** the interface is now HeroUI (React) in a
  WebView2 window, served by Tandem on loopback ([ADR-0010](adr/0010-heroui-web-front-end.md),
  replacing PySide6 + QML). Built so far: device grid, PIN pairing sheet, tray menu, and
  Settings with a theme choice and a window-background picker (neutral tones or gradients).
  Design tokens are checked for WCAG AA on every background. The window now runs on the real
  engine (`tandem.bridge`): it lists the devices on the network, connects and disconnects them,
  and pairs an Apple TV with both of its PINs (remote control, then AirPlay); the appearance is
  saved in the engine's settings. `--demo` still shows invented devices. Hardware check: the
  maintainer paired the Apple TV from the window (both PINs) and it connected. The wrong-PIN
  retry is still unchecked on hardware. Next for the UI: the onboarding checklist.
- **In parallel, Phase 6 Music (started, docs and spikes only):** a new phase after the
  multi-output router; the phases after it moved down by one. Boundaries in
  [ADR-0013](adr/0013-music-integration-boundaries.md). Music spike 1: Windows' media controls
  read and control the Apple Music app (status, timeline, artwork, play and pause, with change
  events and no polling) ([findings](spikes/music-media-sessions.md)). Music spike 2: inside
  Tandem's WebView2 window, Widevine (software) and PlayReady load and build licence
  requests, so full-track MusicKit JS playback is possible in principle; sign-in popups need
  Tandem to stop pywebview sending new windows to the browser
  ([findings](spikes/music-webview2-drm.md)). Now playing is built: Music tab, bar and tray
  controls (see Phase 6). The Apple Music token test and Apple Music browsing are on hold
  (needs a paid Apple Developer membership; resumes if the maintainer joins). The now-playing
  bar passed its exit test with the Apple Music app and a browser. The local player and radio
  are in the window too (This PC, Radio and Queue in the Music tab); their speaker check is
  still to run. Apple Music catalog search is built too (Apple's keyless Search API; results
  open in the Apple Music app; Apple's terms in the 2026-11-08 note on ADR-0013). **Next for
  Music:** the speaker check, the catalog search's link check (does a song link play, or only
  open its page?), then Connections and Spotify.

## Scope

**In scope**
- Windows 11 and Windows 10 22H2+ (x64)
- Sending to AirPlay receivers: discovery, pairing, Apple TV remote control
- System audio to any mix of AirPlay outputs **and** the PC's own speakers, in sync
- Sending video files and links to Apple TV
- Music (Phase 6): now playing and remote control for any music app, Spotify through its Web
  API, a player for local files and internet radio, and Apple Music catalog search that opens
  results in the Apple Music app (ADR-0013). Apple Music library browsing is on hold until the
  maintainer has an Apple Developer membership
- Screen mirroring: shelved — no legitimate open-source path (FairPlay-gated); see ADR-0006
- Smart home and commands (Phase 10): a typed command bar, Tandem as a Home bridge, offline
  voice input, and control of plugs, lamps and TV power
- Apple-inspired, accessible UI with a system tray menu; English first, translation-ready

**Out of scope** (revisit only after v1.0, if users ask)
- Chromecast / Google Cast
- Receiving AirPlay (Windows acting as a speaker or screen)
- macOS, Linux, mobile or Windows on ARM builds
- Mirroring DRM-protected video (streaming services block capture; it shows as black)
- Any telemetry

## Principles

1. **Test the riskiest parts first, build in dependency order.** Phase 0 checks every risky
   protocol, mirroring included, before the architecture is fixed.
2. **Build on what's already proven.** [pyatv](https://github.com/postlund/pyatv) handles discovery, pairing,
   Apple TV control and AirPlay audio. We write our own protocol code only where it falls short.
3. **The engine and UI are separate layers.** The UI never speaks a protocol directly.
4. **Every phase has exit criteria**, checked on real hardware.
5. **Public from day one, private by design.** See [PRIVACY.md](PRIVACY.md). Nothing that identifies
   a contributor, their home or their network is ever committed.

## Reference test hardware

Apple TV 4K (2nd gen), HomePod mini ×2 (not stereo-paired), a third-party AirPlay 2 surround
soundbar, a Raspberry Pi 3 for open-source test receivers, and a Windows 11 laptop with an NVIDIA
GPU (NVENC) on Wi-Fi. Other AirPlay devices on the network (e.g. smart TVs) are excluded from
testing for now.

## Architecture

```
┌──────── UI layer (React + HeroUI in a WebView2 window, ADR-0010) ────────┐
│ Device grid · Pairing · Settings · Remote · Audio router  (web/)         │
└─────────────────────────────────▲────────────────────────────────────────┘
                                  │ WebSocket on 127.0.0.1 (token, origin check)
┌─────────────────────────────────┴────────────────────────────────────────┐
│ UI host (Python): loopback server · controller (UI logic, unit-tested)  │
│ pywebview window · pystray tray menu                                     │
└─────────────────────────────────▲────────────────────────────────────────┘
                                  │ async service API + event bus
┌─────────────────────────────────┴────────────────────────────────────────┐
│ Engine (asyncio)                                                         │
│  Discovery (mDNS) · Device registry · Pairing + credential vault (DPAPI) │
│  Session manager (connect / reconnect / state machine)                   │
│  Protocol adapters: Companion · AirPlay 2 audio · Media URL · Mirroring  │
│  Audio router: capture → fan-out to AirPlay outputs + local speakers     │
│  Music: media sessions (GSMTC) · local player + radio · service APIs     │
│  Video pipeline: screen/window capture → H.264 (NVENC / QSV / AMF / x264)│
│  Platform: firewall rules · startup · logging · redacted diagnostics     │
└──────────────────────────────────────────────────────────────────────────┘
```

Decisions are recorded in [docs/adr](adr/).

## Phases

Model: **Opus 5.5 at high effort** for all work (quality over token cost). Phases marked
**hardest** may use extra-high effort for difficult debugging.

### Phase 0 · Environment check and risk spikes
- [x] Dev environment check; device discovery scan (all reference devices found)
- [x] Privacy guardrails: `.gitignore`, PII/secret pre-commit hooks, redaction policy
- [x] Spike A: pair with Apple TV over Companion; remote commands; now-playing ([go](spikes/spike-a-apple-tv.md))
- [x] Spike B: play a test tone on the soundbar, then each HomePod mini ([go](spikes/spike-b-audio.md))
- [x] Spike C: WASAPI loopback capture; virtual audio device options (ADR-0005) ([go, with a limit](spikes/spike-c-loopback.md))
- [x] Spike D: mirroring feasibility ([no-go: FairPlay-gated, Phase 8 shelved](spikes/spike-d-mirroring.md); ADR-0006)
- [x] Spike E: NVENC H.264 screen encode latency ([go for 1080p; 4K60 needs a GPU-only path](spikes/spike-e-encode.md))
- [x] Spike F: Raspberry Pi 3 as test receiver (shairport-sync) ([go in classic AirPlay mode; AirPlay 2 path stays a hardware check](spikes/spike-f-pi-receiver.md))
- **Exit:** go/no-go table per feature; ADRs accepted; risk register updated.
  **Met** ([Phase 0 summary](spikes/phase-0-summary.md)).

### Phase 1 · Core engine
Device registry, continuous discovery, connection state machine with reconnect and backoff, pairing
flows, encrypted credential vault, event bus, settings, structured logging, redacted diagnostics
bundle, developer command-line tool.
**Exit:** the command-line tool discovers, pairs, connects and disconnects all reference devices
reliably, with ≥80% test coverage of the engine core.
- [x] Package skeleton, tooling (ruff, pyright strict, pytest) and Windows CI
- [x] Event bus, device registry, continuous discovery
- [x] Connection state machine with reconnect and backoff
- [x] Settings, redacted structured logging, DPAPI credential vault (ADR-0007)
- [x] Developer tool: `discover`, `watch`
- [x] Engine service API; pairing flow (PIN entry) saved to the vault; `pair`, `connect` (then
  disconnect), `forget` commands
- [x] Redacted diagnostics bundle (`diagnose`)
- [x] Exit check on the reference devices (one pass; a 5-second scan finds them all)

### Phase 2 · UX design and UI shell
Apple-inspired design system: generous corner radii, soft depth, translucent surfaces, fluid
spring animations, SF-style type scale on Segoe UI Variable, light and dark mode. Accessibility
(keyboard, screen reader, WCAG AA contrast) and text ready for translation. Screens: app shell,
tray quick menu, device grid, PIN pairing sheet, onboarding checklist (detects Home app
access-setting problems), settings.
**Exit:** first-run pairing completed by a tester without help.

### Phase 3 · Apple TV control
Remote pad, swipe area, keyboard entry, now-playing card, app launcher, power and volume.
- [x] Engine control API: `Engine.controls()`, capabilities and push events (ADR-0009)
- [x] Remote keys, media commands, seek, now-playing, artwork, power, apps, text entry
- [x] Volume as level, steps or none; the Apple TV offers steps only (ADR-0009)
- [x] Developer tool: `controls`, `remote`, `media`, `playing`, `power`, `volume`, `apps`,
  `launch`, `type`
- [x] Live check on the Apple TV: keys move the selection, play and pause work, now-playing
  follows; volume reports none (the TV's volume is set by IR from the Siri Remote)
- [x] UI: remote pad, now-playing card, power and volume on the new front end
- [ ] UI check on the Apple TV (remote pad, now-playing, apps, keyboard)
- [x] UI: app launcher and text entry (keyboard opens when the TV asks for text)

### Phase 4 · Audio to one device
Capture → 44.1 kHz/16-bit → ALAC/AAC → AirPlay 2 session. Volume sync, metadata, latency setting.
Tested in order: shairport-sync on the Pi, then the soundbar, then a HomePod mini.
**Exit:** one hour with no dropouts, <5% CPU, survives Wi-Fi blips. **🚩 v0.1 alpha.**
- [x] Pipeline: shared WASAPI loopback capture, a jitter buffer per output, live PCM into
  pyatv's sender (ADR-0011)
- [x] Engine API: `start_audio`, `stop_audio`, `audio_stats`, `AudioStreamChanged` events;
  resumes after a dropped connection
- [x] Developer tool: `stream`
- [x] Pi (shairport-sync, classic): stream timing matches real time
- [x] Pi: a 30 s tone played on the PC arrives clean: exact length, 440 Hz, no gaps or
  glitches, 74 dB signal-to-noise (loopback resampling sets the floor)
- [x] Soundbar, then a HomePod mini, by ear: no crackles or gaps. Lag: 0.5 to 1 s on the
  soundbar; about 5 s on the HomePod mini after trimming Tandem's own start-up backlog
  (known issue, see below)
- [ ] Latency: find where the HomePod's ~5 s comes from (receiver buffer, pyatv's latency
  setting) and bring it down; needed before Phase 5's local-speaker delay
- [x] One hour to the Pi: 3600.0 s received for 3600 s sent, nothing dropped, buffer steady
  at about 100 ms (no clock drift to speak of), 3 brief underruns (0.8 s in total, at one
  moment), 3.0% CPU
- [ ] Wi-Fi blip on real hardware (resuming after a drop is covered by tests only)
- [ ] Windows volume and mute (capture follows them; ADR-0005)

### Phase 5 · Multi-output audio router (hardest)
Pick any combination of outputs: AirPlay devices **and** the PC's own speakers. Local output is
delayed to match the AirPlay buffer so everything plays in sync. Per-output volume, saved groups.
**Exit:** HomePods, soundbar and PC speakers stay within ~20 ms of each other for 30 minutes.
- [x] PC sound devices as outputs next to AirPlay, per-output volume and delay, saved per output
  (ADR-0015)
- [x] Audio panel in the window; command-bar "send audio" and "stop streaming"
- [ ] Exit check on the reference devices (lined up by ear with the delay sliders; no automatic
  sync yet)

### Phase 6 · Music
A Music tab where Tandem is a remote for Spotify and Apple Music and its audio router carries
their sound, plus a player for local files and internet radio, plus Apple Music browsing.
Boundaries in [ADR-0013](adr/0013-music-integration-boundaries.md): the official apps play
streamed music; Tandem never plays or records Spotify streams itself. Depends on Phase 4 and,
for several speakers at once, Phase 5. (Added after Phase 5; the later phases moved down by
one.)
- [x] Spike: media sessions. Read now playing and send play, pause and skip through Windows'
  media controls.
  **Exit:** the Apple Music app shows the right title and artwork and obeys the controls.
  Passed ([findings](spikes/music-media-sessions.md)). The Spotify app isn't tested
  separately: it uses the same media controls, so the maintainer chose to take the Apple Music
  result as covering it. A browser tab is checked in the now-playing bar's exit test (titles and change
  events passed; its controls are still to try).
- [x] Now-playing bar on the Music tab and in the tray menu, for any app.
  **Exit:** it updates within a second of a track change, with the Apple Music app and with a
  browser tab. Built: a **Music** tab (artwork, title, artist and album, a position slider
  when the app allows seeking, previous / play-pause / next), a compact bar on the other tabs
  and play/pause and next in the tray menu. Light and dark, checked with the demo's invented
  music. **Browser: passed** with a quiet test-tone page changing track every 12 s: every
  change reached the window within Windows' clock resolution (about 16 ms)
  (`spikes/now_playing_latency.py`). That check found and fixed two browser quirks: a session
  briefly vanishing on a track change (now a 1 s grace instead of the bar blinking out) and a
  session re-made with the same app id (now re-hooked every time). **Apple Music: passed**
  (2026-11-06, while the maintainer played songs): 5 track changes (skips sent through
  Windows' media controls, each confirmed by a new track), max 16 ms, mean 6 ms, with artwork
  each time; playback was left running.
- [ ] Local player and internet radio: folder picker, library index, queue, radio search;
  plays straight to the chosen speakers. **Exit:** an album plays gaplessly to the soundbar and
  a HomePod mini; a radio station plays for an hour without dropouts.
  Built: the Music tab has **This PC** (music folders, an album grid with artwork, artists,
  song search, an album page with play / play next / add to queue), **Radio** (search of the
  public Radio Browser directory, MP3 and Ogg stations, saved stations) and **Queue**, with a
  player strip on top that shows where the sound goes. Tags come from tinytag and are cached in
  `library.json`; artwork is read from the files into memory. Tracks join without a gap: one
  player thread and one real-time clock across tracks. Checked on this PC without speakers: a
  scan of test files, gapless decoding (6.00 s of 6.0 s of audio, no pauses, after fixing a
  decoder bug that dropped each track's first 23 ms) and a live radio search. **To run:** an
  album to the soundbar and a HomePod mini, and a station for an hour.
- [ ] Connections tab and Spotify: PKCE sign-in, vault storage, library, playlists, search,
  play on a Spotify Connect device, transfer playback. **Exit:** a tester sets up their own
  Spotify developer key and plays a playlist without help.
- [ ] **On hold** (needs a paid Apple Developer membership; resumes if the maintainer joins). Spike: Apple Music in
  Tandem's window. Can MusicKit JS sign in and play full tracks in WebView2? **Exit:** a go or
  no-go, recorded in an ADR. Started: the copy-protection check passed and sign-in popups
  need a small host change; a test with a real developer token is next
  ([findings](spikes/music-webview2-drm.md)).
- [ ] **On hold** (needs a paid Apple Developer membership; resumes if the maintainer joins). Apple Music browsing (only
  on a go): catalog and library browsing; playback handed to the Apple Music app unless the
  spike shows full tracks play in the window. Meanwhile Apple Music works through now playing
  and the router, like any other app.
- [ ] Apple Music catalog search without a key (ADR-0013, 2026-11-08 note): Apple's public
  Search API, songs and albums with artwork beside Apple's "Listen on Apple Music" badge (both
  fetched at run time, kept in memory), no previews, at most 20 searches a minute; a result
  opens in the Apple Music app through its `music://` link. **Exit:** a search finds a known
  song and opening it plays it in the Apple Music app, heard on the speakers through the
  router. Built, with tests on fakes and a demo source. **To run:** the link check (with the
  maintainer's OK, since it plays from their account); until then the button says "Open in
  Apple Music".

### Phase 7 · Send media to Apple TV
Local files via a built-in web server, or URLs; seek bar, queue.
- [x] Engine: a file shared on a random path, or a link, played with AirPlay's play-URL (ADR-0015)
- [x] Send sheet on a connected Apple TV: file picker, link, what's playing, stop
- [ ] Hardware check: an MP4 from the PC and a direct link on the Apple TV

### Phase 8 · Screen mirroring — SHELVED (blocked by FairPlay; ADR-0006)
Spike D found no legitimate open-source path to send AirPlay screen mirroring: the video is
keyed by FairPlay, and we will not reverse-engineer or bypass it in a public project. Parked
unless a legitimate path appears. If reopened: whole screen first, then a single window;
resolution and frame-rate presets; encoder selection; audio and video in sync; targets 1080p30
at <250 ms, stretching to 4K/60. (Sending video files and links to the Apple TV, Phase 7, is
unaffected and needs no FairPlay.)

### Phase 9 · Hardening and v1.0
Installer with firewall rules, auto-update via GitHub Releases, code signing (SignPath
Foundation, free for open source), docs site, contributor docs, reproducible builds.
- [x] Installer around Python's embeddable runtime, with firewall rule and WebView2 (ADR-0017)
- [x] CI builds, installs, smoke-tests and uninstalls it; a `v*` tag publishes a pre-release
- [x] One window per user; Getting started checklist on first run
- [x] Pinned, tested library versions in every build (1.1.0, after 1.0.0 shipped a breaking one)
- [ ] Code signing (SignPath Foundation; needs the maintainer to apply; the release workflow
  is ready: docs/signing.md)
- [x] Update check (the window links to new releases; installing stays manual)

### Phase 10 · Smart home and commands
Tandem can't call Siri: there's no supported way in from Windows, and we won't reverse-engineer
one (ADR-0014). Instead: Tandem's own command bar, and Tandem in the Home app so Siri on a
HomePod can drive it. Targets for home control: smart plugs, lamps and TV power. Each step is
its own PR with its own gate.
- **10a · Typed command bar.** A command bar in the window (Ctrl+K), a local parser with a fixed
  set of verbs, and device names from the registry. Needs nothing beyond Phases 3 to 5.
  **Gate:** 20 sample commands run correctly on the reference devices.
  - [x] Parser, dispatcher and command bar (demo-checked)
  - [ ] Gate on the reference devices
- **10b · Tandem as a Home bridge (spike).** Tandem shows in the Home app as a bridge with a
  few switches; Siri on a HomePod flips them, and Home automations on them let Tandem control
  Home devices. Off by default; pairing keys in the encrypted vault.
  **Gate:** a Home automation turns a lamp off from Tandem, and the hands-on Siri test passes.
  - [x] Bridge with Tandem Audio, Music and TV switches, DPAPI-encrypted keys (ADR-0016)
  - [ ] Gate on the reference devices
- **10c · Offline voice input.** A push-to-talk microphone button and hotkey for the command
  bar, using Windows' on-device recognizer with a phrase list. Microphone off by default
  (opt-in in Settings), no audio saved or sent; never the WebView2 browser speech API (it is
  online). **Gate:** 18 of the 20 sample commands recognized by voice in a quiet room.
- **10d · Direct device control (optional).** Devices not in Apple Home through aiohomekit
  (HomeKit allows one controller per accessory), and a Matter multi-admin spike on Windows.
  **Gate:** go or no-go after the spike, only if the maintainer has such devices.

## Quality strategy
- **Unit tests** use recorded protocol exchanges (scrubbed of identifiers).
- **Integration tests** run against an open-source receiver: shairport-sync for audio, in classic
  AirPlay mode (Spike F); the AirPlay 2 path is checked on the real speakers. (UxPlay
  was the mirroring test target; mirroring is shelved, see ADR-0006.)
- **Hardware checklist** run by the tester after every phase.
- **Performance targets:** discovery <3 s, cold start <2 s, near-zero CPU at idle, <200 MB RAM while streaming audio.

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| FairPlay encryption blocks mirroring | High | Confirmed in Spike D; Phase 8 shelved (ADR-0006). Rest of the app doesn't depend on it |
| tvOS / HomePod updates break protocols | Medium | Track pyatv upstream; version-gated code paths |
| Home app access setting blocks connections | Medium | Onboarding detects it and guides the fix |
| Multi-output drift (incl. PC speakers) | Medium | Shared clock, delay compensation, manual offset per output |
| AirPlay latency too high for comfortable use (HomePod ~5 s in Phase 4) | Medium | Measure the receiver buffer and pyatv's latency setting; tune before Phase 5 |
| Virtual audio driver licensing/signing | Medium | ADR-0005 accepted: no open-source signed driver exists; users install one (e.g. VB-CABLE) themselves; loopback works without it |
| Test receiver can't take pyatv's AirPlay 2 stream (NTP vs PTP timing) | Medium | Spike F: Pi tests cover classic AirPlay; the AirPlay 2 path stays on the hardware checklist; Phase 5 checks early whether NTP timing holds multi-speaker sync |
| 4K60 video needs frames kept on the GPU, which PyAV can't do | Low (mirroring shelved) | Spike E: 1080p works from Python; a small native helper would carry 4K60 if Phase 8 reopens |
| Unsigned builds trigger SmartScreen or are blocked by Smart App Control | High | SignPath code signing; until then, test from source with signed `python.exe` |
| Smart App Control blocks a newly released native npm binary in the front-end toolchain | Medium | Pin the last version that loads (`overrides` in `web/package.json`); end users never run Node |
| WebView2 runtime missing on an older Windows 10 PC | Low | Ships with Windows 11 and with Edge on Windows 10; the Phase 9 installer adds Microsoft's bootstrapper |
| Spotify tightens developer access again (it did in Nov 2024, Mar 2025, Feb 2026) | Medium | Spotify is a remote only and each user brings their own key (ADR-0013); now playing, the local player and radio don't depend on it |
| Apple Music full tracks won't play in Tandem's window | Medium | Music spike 2: Widevine works in WebView2 on this PC; a token test decides. Fallback: browse in Tandem, play in the Apple Music app (ADR-0013) |
| Contributor privacy leak in public repo | Medium | PRIVACY.md, pre-commit PII + secret scanning, redacted logs |
| Trademark complaint | Low | Neutral name, plain compatibility wording |
