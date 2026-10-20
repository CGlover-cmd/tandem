# Spike B: test tone on the soundbar and HomePod minis

**Result: go.** pyatv streams audio from Windows to the soundbar and both HomePod minis, with no
pairing and no protocol code of our own.

Script: [spikes/spike_b_audio.py](../../spikes/spike_b_audio.py)

## Setup

- Third-party AirPlay 2 surround soundbar; HomePod mini ×2 (not stereo-paired) on software 27.2
- Windows 11 laptop on Wi-Fi, Python 3.11, pyatv 0.18.0
- Tone: 5 s, 440 Hz sine, 44.1 kHz/16-bit stereo WAV made by the script, sent with
  `stream.stream_file` (RAOP), volume set to 30% before streaming
- The tester was in the room and confirmed each tone by ear

## Findings

| Check | Soundbar | HomePod 1 | HomePod 2 |
|---|---|---|---|
| Found by kind, not name | Pass | Pass | Pass |
| Pairing needed | No | No | No |
| Connect | 0.0 s | 0.4 s | 0.3 s |
| Tone heard, clean | Pass | Pass | Pass |
| Stream call, total (5 s tone) | 9.7 s | 8.4 s | 7.5 s |

## What this means for later phases

- **No pairing for audio (Phase 2).** None of these speakers asked for a PIN, and the Home app
  access setting did not get in the way. Onboarding still needs to handle speakers that do ask.
- **Picking the soundbar.** It reports no model pyatv knows, so the spike picked it as the one
  non-Apple device that accepts RAOP streams. The device registry (Phase 1) should classify
  devices by the services they offer, not only by model.
- **Start-up overhead.** Each stream call took 2.5 to 4.7 s longer than the tone. That covers
  session setup, buffering and the device draining its buffer, which Phase 4 must measure
  separately to set the latency target and the delay for local speakers (ADR-0005).
- **Volume before streaming.** pyatv accepts a level before the stream starts and applies it
  at setup, so a stream need not start at the device's previous (possibly loud) level. The
  level heard was not measured; Phase 4 should check it matches.
- Not tried yet: a continuous live stream (Phase 4), several outputs at once and their sync
  (Phase 5), metadata and artwork shown on the device, and volume changes mid-stream.
