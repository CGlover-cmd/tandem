# Spike D: screen-mirroring feasibility

**Result: no-go for now, pending a decision.** An AirPlay receiver will accept screen
mirroring, but there is no open-source path to *send* it: pyatv streams audio and plays media
URLs, not mirroring, and the mirroring video stream is keyed by FairPlay (the AirPlay
`fp-setup` step), Apple's content protection. This spike deliberately does not implement or
bypass FairPlay. Whether Phase 8 proceeds is a maintainer decision, captured in
[ADR-0006](../adr/0006-screen-mirroring-fairplay.md).

Script: [spikes/spike_d_mirror.py](../../spikes/spike_d_mirror.py)

## Setup

- Raspberry Pi 3 (wired Ethernet) running UxPlay 1.71 as a test mirroring receiver, under a
  neutral name, with video and audio sinks set to `fakesink` (no display needed)
- Reference Apple TV 4K on the same network
- Windows 11 laptop on Wi-Fi, Python 3.11, pyatv 0.18.0
- The spike only reads discovery data and checks library capabilities; it sends nothing to
  either device and completes no pairing

## What the spike checks

1. Find a receiver by the services it advertises, never by name.
2. Read the receiver's advertised AirPlay `features` value from mDNS (public capability data).
3. Check what pyatv exposes for *sending* video.

## Findings

| Check | UxPlay (Pi) | Apple TV | Notes |
|---|---|---|---|
| Found by service, not name | Pass | Pass | UxPlay: AirPlay + RAOP, no Companion; Apple TV: AirPlay + Companion + RAOP |
| Advertises screen mirroring | Yes | Yes | Both are mirroring receivers |
| pyatv can send a media URL / file | Yes | Yes | `Stream.play_url` — this is Phase 7, not mirroring |
| pyatv can stream audio | Yes | Yes | `Stream.stream_file` — Phase 4 |
| **pyatv can send screen mirroring** | **No** | **No** | pyatv implements no mirroring *sender* |

## What this means for later phases

- **Phase 8 (screen mirroring) is gated here, as the roadmap and risk register predicted.**
  The receiver side is willing; the sender side does not exist in our stack. To mirror, Tandem
  would have to speak the AirPlay mirroring protocol itself, and that protocol encrypts the
  video with a key set up through FairPlay (`fp-setup`). Open-source *receivers* (UxPlay,
  RPiPlay) handle FairPlay on the receive side using recovered key material; we are not aware
  of an open-source *sender* implementation, and reproducing one would mean reverse-engineering
  Apple's content protection. For a public project that is both a legal risk and out of step
  with the project's values, so this spike stops at the boundary.
- **This does not affect the rest of the app.** Discovery, pairing, Apple TV control (Spike A),
  audio out (Spike B), loopback capture (Spike C) and sending media files/URLs (Phase 7) are
  all independent of FairPlay and remain feasible. Only screen mirroring is blocked.
- **The decision is the maintainer's**, recorded in
  [ADR-0006](../adr/0006-screen-mirroring-fairplay.md): shelve Phase 8 mirroring unless a
  legitimate path appears (for example a signed virtual-display driver plus a receiver that
  takes an unprotected stream, or an officially sanctioned route), and keep building the
  FairPlay-free features that make up the alpha.

## Not covered here

- No pairing was completed and no stream was attempted against either device.
- Spike E (NVENC H.264 encode latency) is unaffected and still worth doing: if a legitimate
  mirroring path ever opens, the encode pipeline is the same work. It is independent of this
  no-go.
