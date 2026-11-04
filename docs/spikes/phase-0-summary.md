# Phase 0 summary: go/no-go per feature

Phase 0 tested every risky part of the plan on the reference hardware before the architecture
is fixed. Six spikes ran; all the decisions they raised are recorded as accepted ADRs.

| Feature | Verdict | Evidence | Carry into |
|---|---|---|---|
| Find devices on the network | **Go** | All reference devices found by kind, never by name (discovery scan, Spikes A–F) | Phase 1: classify by services and model string, not by "the one unknown speaker" (Spikes B, F) |
| Pair with and control the Apple TV | **Go** | Pairing, remote keys, power and now-playing work through pyatv ([Spike A](spike-a-apple-tv.md)) | Phases 1, 3 |
| Stream audio to AirPlay speakers | **Go** | Clean tone on the soundbar and both HomePod minis, no pairing ([Spike B](spike-b-audio.md)) | Phase 4 |
| Capture the PC's own audio | **Go, with a limit** | WASAPI loopback, no gaps, low CPU; it follows the Windows volume and mute ([Spike C](spike-c-loopback.md), [ADR-0005](../adr/0005-multi-output-audio-routing.md)) | Phase 4: loopback by default; a user-installed virtual audio device to send to AirPlay with the PC's speakers silent |
| AirPlay speakers and PC speakers in sync | **Go, unproven** | The pieces work separately (Spikes B, C); sync itself is Phase 5's job. pyatv times each stream with NTP, not the shared PTP clock AirPlay 2 speakers use ([Spike F](spike-f-pi-receiver.md)) | Phase 5: check early whether NTP timing holds ~20 ms across speakers |
| Send video files and links to the Apple TV | **Go, untested** | pyatv offers `play_url`; not exercised yet ([Spike D](spike-d-mirroring.md)) | Phase 7 |
| Screen mirroring | **No-go** | FairPlay-gated, no legitimate open-source sender ([Spike D](spike-d-mirroring.md), [ADR-0006](../adr/0006-screen-mirroring-fairplay.md)) | Phase 8 shelved |
| Hardware video encode | **Go for 1080p** | Capture, NVENC encode and decode back in about 60 ms; 4K60 needs a GPU-only path ([Spike E](spike-e-encode.md)) | Only if mirroring reopens |
| Automatic audio tests | **Go, classic AirPlay only** | shairport-sync on the Pi receives pyatv's stream bit-exact; it can't take pyatv's AirPlay 2 stream ([Spike F](spike-f-pi-receiver.md)) | Phase 4 integration tests; the AirPlay 2 path stays on the hardware checklist |
| Smart-home control | **Not assessed** | Out of Phase 0 by plan | Phase 10 starts with its own feasibility spike |
| Windows 10 22H2 | **Not tested** | All spikes ran on the Windows 11 test laptop | Phase 1: add a Windows 10 check to the hardware checklist when a test machine is available |

## Decisions

All six ADRs are accepted: [0001](../adr/0001-python-engine-on-pyatv.md) Python engine on
pyatv, [0002](../adr/0002-pyside6-qml-ui.md) PySide6 + QML,
[0003](../adr/0003-license-gpl-3.md) GPL-3.0-or-later,
[0004](../adr/0004-public-repo-privacy-guardrails.md) public repo with privacy guardrails,
[0005](../adr/0005-multi-output-audio-routing.md) multi-output audio routing,
[0006](../adr/0006-screen-mirroring-fairplay.md) screen mirroring shelved. (ADR-0007, the
engine core and credential vault, belongs to Phase 1.)

The risk register in the [roadmap](../ROADMAP.md#risk-register) carries each spike's findings.
