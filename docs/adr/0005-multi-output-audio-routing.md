# ADR-0005: Multi-output audio routing

- Status: Accepted (after Phase 0 Spike C)
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

## What Spike C found
([findings](../spikes/spike-c-loopback.md))
- Loopback works from Python through miniaudio (already a pyatv dependency): steady delivery,
  1.5% of one core, tens of milliseconds of latency, near-free conversion to 44.1 kHz/16-bit.
- On the test laptop loopback follows the Windows volume, and mute gives pure silence. So
  loopback alone also can't do "AirPlay only, PC silent".
- No open-source virtual audio driver is signed for Secure Boot on Windows 11. VB-CABLE is
  signed and free for users to install themselves; bundling it needs an agreement.

## Decision
Option 3, hybrid:
- **Default: loopback** of the default output through miniaudio. Works with no install. AirPlay
  plays along with the PC speakers, and the user is told that the PC volume and mute also
  affect AirPlay (compensating for the volume level where possible).
- **Optional: a virtual audio device the user installs themselves**, documented with VB-CABLE as
  the example. Set as the Windows default, it unlocks "AirPlay only, PC silent" and in-sync
  "PC speakers + AirPlay" (Tandem plays the delayed audio to the real speakers). Tandem detects
  it and guides the setup, but does not bundle or install it.
- **Not now: our own driver.** Revisit after v1.0 if signing becomes affordable, or if a
  suitable signed open-source driver appears.

## Consequences
- v0.1 needs no driver and no admin rights for audio.
- The full multi-output experience (Phase 5) needs a one-time install of third-party software,
  which onboarding must explain.
- Open: Windows 11 per-app capture (process loopback) might give "AirPlay only, PC silent"
  without a driver on Windows 11. Try it in Phase 4; it can't help Windows 10 22H2.
