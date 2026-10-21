# ADR-0009: Device controls API and the volume fallback

- Status: Accepted
- Date: 2026-10-21

## Context
Phase 3 adds Apple TV control: remote keys, media commands, now-playing, power, apps and text
entry. The UI is being rebuilt (a new front end), so the engine needs a control API it can
build against without knowing pyatv. Spike A showed two complications. First, what an Apple TV
offers changes with what's playing (36 features idle, 50 while a video plays). Second, it
offered no volume control at all. In Phase 3 the reference Apple TV offered volume up/down
steps once while asleep, and nothing while awake. Its Volume Control setting is *Auto via IR
(TV)*: the Siri Remote changes the TV's volume by infrared, so nothing on the network can.

## Decision
- **One facade per device:** `Engine.controls(device_id)` returns `DeviceControls`. It stays
  valid across reconnects because it looks up the live controller on each call. Commands raise
  `NotConnectedError` when the device isn't connected and `UnsupportedError` when it doesn't
  offer the capability right now, before anything is sent.
- **Capabilities, not features:** the engine exposes a small `Capability` set (remote, play,
  pause, seek, now-playing, power, apps, text entry and so on) mapped from pyatv features in
  `adapters/pyatv_control.py`. A capability counts only when every feature it needs is
  available.
- **Push, never poll:** on connect the engine attaches a controller and publishes
  `ControlsAvailable` with the starting state. After that it publishes `NowPlayingChanged`,
  `PowerChanged`, `VolumeChanged` and `CapabilitiesChanged` (rechecked after every push),
  then `ControlsUnavailable` on disconnect.
- **Volume is one of three kinds** (`VolumeControl`): `LEVEL` (exact 0 to 100, with the current
  level), `STEPS` (up and down only, no level), or `NONE`. `volume_up`/`volume_down` work for
  LEVEL and STEPS; `set_volume` only for LEVEL. With NONE the UI hides volume controls and explains
  why: an Apple TV that changes volume by infrared leaves it to its own remote. The fix, where
  the TV supports it, is an HDMI-CEC option under Settings > Remotes and Devices > Volume
  Control.
- **Media titles are personal.** They're never logged, and the developer tool hides them unless
  `--show-private` is given.

## Consequences
- A UI shows a slider only for LEVEL, plus/minus buttons for STEPS, and a hint for NONE. It must
  follow `CapabilitiesChanged`, because play controls appear and disappear with playback.
- On the reference setup (IR volume) Tandem can't change the TV's volume at all. That's a limit
  of the setup, not something the engine can work around. Where an Apple TV offers steps over
  HDMI-CEC, it can't report a level, so the UI shows plus and minus without a slider.
- Adding another protocol library later means writing one more `Controller`; the facade, events
  and UI stay as they are.
