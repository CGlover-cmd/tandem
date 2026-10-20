# Tandem roadmap

An open-source Windows app that sends audio, video and your screen to AirPlay devices
(Apple TV, HomePod, AirPlay 2 speakers and TVs), with a polished Apple-inspired interface.
Smart-home control (HomeKit / Matter) follows once the AirPlay core is solid.

> Name: **Tandem**. Names and branding must not use Apple trademarks (AirPlay, Apple, HomePod,
> HomeKit). We describe compatibility in plain words, e.g. "works with Apple TV and HomePod".

## Status and next step

_Update this section at the end of every working session._

- **Current phase:** 0, environment check and risk spikes.
- **Done:** dev environment, device discovery (all reference devices found), privacy guardrails,
  public repo with GitHub secret scanning and push protection. Spike A passed: pairing, remote
  keys, power and now-playing all work on the Apple TV ([findings](spikes/spike-a-apple-tv.md)).
  Spike B passed: a test tone streamed cleanly to the soundbar and both HomePod minis, with no
  pairing ([findings](spikes/spike-b-audio.md)).
- **Next:** Spike C, WASAPI loopback capture and the virtual audio device options (ADR-0005).

## Scope

**In scope**
- Windows 11 and Windows 10 22H2+ (x64)
- Sending to AirPlay receivers: discovery, pairing, Apple TV remote control
- System audio to any mix of AirPlay outputs **and** the PC's own speakers, in sync
- Sending video files and links to Apple TV
- Screen mirroring: whole screen first, then single windows (experimental, feasibility-gated)
- Smart-home control of plugs, lamps and TV power (Phase 9)
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
┌──────────────────────── UI layer (PySide6 + QML) ────────────────────────┐
│ App shell · Tray menu · Device grid · Pairing · Remote · Audio router    │
│ ViewModels (pure Python, unit-tested)                                    │
└─────────────────────────────────▲────────────────────────────────────────┘
                                  │ async service API + event bus
┌─────────────────────────────────┴────────────────────────────────────────┐
│ Engine (asyncio)                                                         │
│  Discovery (mDNS) · Device registry · Pairing + credential vault (DPAPI) │
│  Session manager (connect / reconnect / state machine)                   │
│  Protocol adapters: Companion · AirPlay 2 audio · Media URL · Mirroring  │
│  Audio router: capture → fan-out to AirPlay outputs + local speakers     │
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
- [ ] Spike C: WASAPI loopback capture; virtual audio device options (ADR-0005)
- [ ] Spike D: mirroring feasibility: pairing and FairPlay setup handshake, against UxPlay first, then Apple TV
- [ ] Spike E: NVENC H.264 screen encode latency
- [ ] Spike F: Raspberry Pi 3 as test receiver (shairport-sync for AirPlay 2 audio)
- **Exit:** go/no-go table per feature; ADRs accepted; risk register updated.

### Phase 1 · Core engine
Device registry, continuous discovery, connection state machine with reconnect and backoff, pairing
flows, encrypted credential vault, event bus, settings, structured logging, redacted diagnostics
bundle, developer command-line tool.
**Exit:** the command-line tool discovers, pairs, connects and disconnects all reference devices
reliably, with ≥80% test coverage of the engine core.

### Phase 2 · UX design and UI shell
Apple-inspired design system: generous corner radii, soft depth, translucent surfaces, fluid
spring animations, SF-style type scale on Segoe UI Variable, light and dark mode. Accessibility
(keyboard, screen reader, WCAG AA contrast) and text ready for translation. Screens: app shell,
tray quick menu, device grid, PIN pairing sheet, onboarding checklist (detects Home app
access-setting problems), settings.
**Exit:** first-run pairing completed by a tester without help.

### Phase 3 · Apple TV control
Remote pad, swipe area, keyboard entry, now-playing card, app launcher, power and volume.

### Phase 4 · Audio to one device
Capture → 44.1 kHz/16-bit → ALAC/AAC → AirPlay 2 session. Volume sync, metadata, latency setting.
Tested in order: shairport-sync on the Pi, then the soundbar, then a HomePod mini.
**Exit:** one hour with no dropouts, <5% CPU, survives Wi-Fi blips. **🚩 v0.1 alpha.**

### Phase 5 · Multi-output audio router (hardest)
Pick any combination of outputs: AirPlay devices **and** the PC's own speakers. Local output is
delayed to match the AirPlay buffer so everything plays in sync. Per-output volume, saved groups.
**Exit:** HomePods, soundbar and PC speakers stay within ~20 ms of each other for 30 minutes.

### Phase 6 · Send media to Apple TV
Local files via a built-in web server, or URLs; seek bar, queue.

### Phase 7 · Screen mirroring (hardest · only if Spike D says go)
Whole screen first, then a single window. Resolution and frame-rate presets, encoder selection,
audio and video in sync. Targets 1080p30 at <250 ms, stretching to 4K/60. Extending the desktop
onto the TV is a stretch goal (needs a signed virtual-display driver).

### Phase 8 · Hardening and v1.0 (can start before Phase 7 finishes)
Installer with firewall rules, auto-update via GitHub Releases, code signing (SignPath
Foundation, free for open source), docs site, contributor docs, reproducible builds.

### Phase 9 · Smart-home control (feasibility spike first)
Targets: smart plugs, lamps and TV power. Accessories already set up in Apple Home generally won't
accept a second controller, so the paths are: Matter multi-admin, HomeKit (HAP) control through
aiohomekit for accessories not set up in Apple Home, or a Home Assistant bridge.

## Quality strategy
- **Unit tests** use recorded protocol exchanges (scrubbed of identifiers).
- **Integration tests** run against open-source receivers: shairport-sync for audio, UxPlay for mirroring.
- **Hardware checklist** run by the tester after every phase.
- **Performance targets:** discovery <3 s, cold start <2 s, near-zero CPU at idle, <200 MB RAM while streaming audio.

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| FairPlay encryption blocks mirroring | High | Known after Phase 0; rest of the app doesn't depend on it |
| tvOS / HomePod updates break protocols | Medium | Track pyatv upstream; version-gated code paths |
| Home app access setting blocks connections | Medium | Onboarding detects it and guides the fix |
| Multi-output drift (incl. PC speakers) | Medium | Shared clock, delay compensation, manual offset per output |
| Virtual audio driver licensing/signing | Medium | ADR-0005; prefer an existing signed driver installed separately |
| Unsigned builds trigger SmartScreen or are blocked by Smart App Control | High | SignPath code signing; until then, test from source with signed `python.exe` |
| Contributor privacy leak in public repo | Medium | PRIVACY.md, pre-commit PII + secret scanning, redacted logs |
| Trademark complaint | Low | Neutral name, plain compatibility wording |
