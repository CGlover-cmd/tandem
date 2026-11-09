# ADR-0020: Mute the PC while AirPlay plays

- Status: Accepted
- Date: 2026-11-09

## Context
Tandem sends the PC's sound to AirPlay by capturing Windows' default output with WASAPI
loopback (ADR-0005, ADR-0011). Windows keeps playing that sound on the PC's own speakers, and
AirPlay is always a couple of seconds behind, so with both on the room hears an echo. The
maintainer asked for the PC to go quiet while AirPlay plays, with a way to turn it back on.

Classic loopback records the output after Windows applies its volume and mute (Spike C), so
muting the speakers silences AirPlay too. Spike G (`spikes/spike_g_process_loopback.py`) tried
the alternatives on the maintainer's PC (Windows 11, build 26200):

- **Process loopback** (Windows 10 2004+, `ActivateAudioInterfaceAsync` on
  `VAD\Process_Loopback`) records the apps' own streams, every process except a given tree,
  before the output's mute. With the speakers muted it captured the test tone at full level,
  and Windows' system sounds too. miniaudio has a switch for this, but the build pyatv pins
  opens it through the wrong path on desktop Windows (error -2), so Tandem talks to Core Audio
  through ctypes.
- **Muting other apps' sessions** (so Tandem could play an in-step copy on the same speakers)
  isn't possible: Windows refused the per-app volume interface (E_NOINTERFACE) on every session.

So the PC's speakers can be muted while AirPlay keeps the sound, but those same speakers can't
play in step with AirPlay: their mute also silences anything Tandem plays there.

## Decision
- **Capture with process loopback** (`adapters/process_loopback.py`), leaving out Tandem's own
  process tree. If it fails to open, `SystemCapture` falls back to classic loopback for the rest
  of the run, and muting is turned off (it would silence AirPlay).
- **Mute Windows' default output while AirPlay plays the PC's sound** (`engine/pc_mute.py`,
  driven by `engine/outputs.py`): when an AirPlay output is streaming (or reconnecting) and the
  source is the PC's own audio. Unmute when the last AirPlay output stops, the source changes,
  the setting is turned off, or Tandem closes. If Windows switches to another output (headphones
  plugged in), that one is muted instead.
- **Only undo our own mute.** An output the user had muted already is left alone, and is not
  unmuted afterwards.
- **Survive being stopped.** The muted output's id is written to `pc-mute.json` in Tandem's data
  folder before muting and removed after unmuting; the next start unmutes it if the file is
  still there.
- **The PC's switch** in the Audio panel shows "Muted while AirPlay plays" (`OutputState.MUTED`).
  Turning it on keeps the PC playing until AirPlay stops ("Playing ahead of AirPlay",
  `OutputState.AHEAD`), not in step. Headphones or another output Tandem plays to are in step.
- **A setting**, Advanced: "Mute this PC while AirPlay plays", on by default (`mute_pc`).

## Consequences
- AirPlay-only listening needs no virtual audio cable. A cable (ADR-0005) is still the way to
  hear the PC's own speakers in step with AirPlay.
- Process loopback also records apps that play to a non-default output, which classic loopback
  of the default output didn't.
- Tandem now changes a Windows setting. If Tandem is killed outright, the PC stays muted until
  Tandem next starts or the user unmutes it in Windows.
- Endpoint ids are the PC's own identifiers: kept in the local data folder, never logged.
- Updates ADR-0005 (no cable needed just to silence the PC) and ADR-0011 (capture source).
