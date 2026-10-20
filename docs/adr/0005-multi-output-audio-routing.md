# ADR-0005: Multi-output audio routing

- Status: Proposed (decided after Phase 0 Spike C)
- Date: 2026-10-20

## Context
Users can pick any combination of outputs at once: several AirPlay devices **and** the PC's own
speakers. AirPlay 2 buffers audio (on the order of seconds), so if Windows keeps playing directly
to the speakers, they run ahead of the AirPlay devices. That makes an echo.

## Options
1. **WASAPI loopback only.** Capture what the default device plays. Simple and needs no driver,
   but the local speakers can't be delayed to match, so "PC speakers + AirPlay" echoes.
2. **Virtual audio device as the Windows default.** Apps play into a virtual device; the app
   captures it and fans out to AirPlay outputs and to the real speakers, delaying the local
   output to stay in sync. Needs a signed driver. Candidates: an existing open-source signed
   driver the user installs separately, or our own driver (needs Microsoft attestation signing
   and an EV certificate, which is costly).
3. **Hybrid.** Loopback by default; the virtual device is an optional install that unlocks
   in-sync local playback.

## Leaning
Option 3: works out of the box, with the best experience behind an optional one-time install.

## To decide in Spike C
Loopback latency and CPU cost, which signed drivers are available and how they can be
redistributed, and the install UX.
