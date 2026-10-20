# Spike C: capturing the PC's own audio

**Result: go, with one limit.** WASAPI loopback captures everything Windows plays, from Python,
with no new packages, no gaps and little CPU. The limit: on the test laptop the capture follows
the Windows volume and mute, so loopback alone can't send audio to AirPlay while the PC's own
speakers stay silent. That and in-sync PC speakers need a virtual audio device (ADR-0005).

Script: [spikes/spike_c_loopback.py](../../spikes/spike_c_loopback.py)

## Setup

- Windows 11 laptop, built-in speakers as the default output, Python 3.11
- miniaudio 1.71 (already installed as a pyatv dependency) on its WASAPI backend. Its Python
  wrapper only offers plain capture, so the spike opens miniaudio's loopback device type itself.
- The tester played music in an ordinary app and changed the volume and mute when asked.
  No captured audio was written to disk.

## Findings

| Check | Result | Notes |
|---|---|---|
| Loopback available | Pass | Default output's native format: 48 kHz, 32-bit float, stereo (16-bit also listed) |
| Open the capture | Pass | 158 ms |
| Latency | Pass | Clicks played by the spike came back in 59.8 to 60.9 ms (median 60.1 ms, 10 of 10). This includes the spike's own playback buffer, so loopback itself is faster |
| Block size | Pass | 480 frames (10 ms) per block |
| 60 s of music | Pass | 100.0% of expected frames, longest gap between blocks 11 ms |
| CPU | Pass | 1.5% of one core while capturing music in Python (0.6% in silence) |
| Convert to 44.1 kHz/16-bit | Pass | 99 ms for 60 s of audio (0.17% of real time), using miniaudio's converter |
| Nothing playing | Pass | Blocks keep arriving, filled with silence; no keep-alive stream needed with miniaudio |
| Level, normal volume | Pass | Tone played at -15.1 dBFS RMS, captured at -16.8 dBFS |
| Level, muted | **Silence** | Captured -inf dBFS: mute cuts the capture off completely |
| Level, 10% volume | **Quieter** | Captured -43.6 dBFS: the volume slider scales the capture |

## What this means for later phases

- **Capture is not the bottleneck (Phase 4).** Delivery is steady, CPU is low even in Python,
  and conversion to AirPlay's format is close to free. The engine can use miniaudio's loopback
  rather than writing WASAPI bindings of its own.
- **Capture follows the Windows volume.** On this laptop the volume is applied before loopback
  sees the audio (some drivers apply it in hardware, after loopback, so other PCs may differ).
  Turning the PC down turns AirPlay down too, and muting the PC silences AirPlay. Phase 4 should
  read the endpoint volume and either compensate (possible above 0%, since the samples are
  float) or tell the user. Mute can't be compensated.
- **"AirPlay only, PC silent" needs more than loopback.** Options, for ADR-0005: a virtual audio
  device set as the Windows default (the PC then makes no sound by itself), or Windows 11's
  per-app capture (process loopback), which may sit before the volume. Process loopback needs
  Windows 11 or Server 2022 (build 20348+), so it can't cover Windows 10 22H2, and it is untested.
- **Latency budget.** Loopback adds tens of milliseconds at most, small next to AirPlay's
  buffer (Spike B saw seconds of start-up overhead). The delay for local speakers (Phase 5) is
  dominated by AirPlay, not capture.

## Virtual audio device options (desk research)

No driver was installed. Findings as of this spike:

| Option | Licence | Signed for Secure Boot on Windows 11 | Notes |
|---|---|---|---|
| VB-Audio VB-CABLE | Donationware for users; bundling needs an agreement with VB-Audio | Yes | The user installs it themselves; widely used |
| VirtualDrivers Virtual Audio Driver | MIT (plus MS-PL sample code) | No: beta, needs test-signing mode | Installed by hand through Device Manager |
| Scream | MS-PL | No on Windows 11 (needs test mode); Windows 10 builds may fail under Secure Boot | Sends audio as network multicast, not built for this use |
| Our own driver (from Microsoft's SysVAD sample) | Ours | Only with Microsoft attestation signing, which needs an EV certificate and a hardware developer account | Costly; revisit after v1.0 |

Asking users to turn on test-signing or turn off Secure Boot is not acceptable. Today the only
practical virtual device is one the user installs themselves, such as VB-CABLE.

## Not tried

- Changing the default output while capturing (plugging in headphones)
- Loopback on a non-default output, and on a PC whose driver applies volume in hardware
- Windows 11 process loopback
- A live capture streamed to an AirPlay device (Phase 4)

Sources: [VirtualDrivers Virtual-Audio-Driver](https://github.com/VirtualDrivers/Virtual-Audio-Driver),
[Scream](https://github.com/duncanthrax/scream),
[VB-Audio licensing](https://vb-audio.com/Services/licensing.htm),
[Microsoft: process loopback parameters](https://learn.microsoft.com/en-us/windows/win32/api/audioclientactivationparams/ns-audioclientactivationparams-audioclient_process_loopback_params).
