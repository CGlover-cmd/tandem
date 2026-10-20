# Spike A: Apple TV pairing, remote control and now-playing

**Result: go.** pyatv pairs with and controls the reference Apple TV from Windows, with no
protocol code of our own.

Script: [spikes/spike_a_appletv.py](../../spikes/spike_a_appletv.py)

## Setup

- Apple TV 4K (2nd gen) on tvOS 27.2, wired Ethernet
- Windows 11 laptop on Wi-Fi, Python 3.11, pyatv 0.18.0

## Findings

| Check | Result | Notes |
|---|---|---|
| Find the Apple TV | Pass | Picked by model; the scan used a fixed 5 s timeout, so discovery time against the <3 s target is still unmeasured |
| Pair over Companion | Pass | 4-digit PIN shown on the TV, entered once |
| Pair over AirPlay | Pass | A second 4-digit PIN; needed for now-playing and media controls |
| Connect with saved keys | Pass | 1.3 to 1.7 s |
| Home and arrow keys | Pass | Confirmed on screen; each press sent in 10 to 17 ms |
| Power off and on | Pass | Confirmed on screen; the reported power state lags a few seconds after waking |
| Pause and play | Pass | Confirmed on screen and by the reported state; sent in 50 to 130 ms |
| Now-playing | Pass | App, play state, media type, title, position and total time, updating live |

## What this means for later phases

- **Pairing UI (Phase 2)** must handle two PIN prompts in a row, one per protocol, and explain why.
- **Feature list depends on what's playing.** With nothing playing the device offers 36 features;
  while a video plays it offers 50 (play, pause, seek, title, artwork and so on appear). The UI
  must react to feature changes, not read them once at connect.
- **Power state** should come from push updates, not a read straight after a command.
- **Volume** was not offered by this Apple TV in either state. Phase 3 needs to check whether
  this depends on the TV's audio output setup.
- **Credentials:** the spike keeps pyatv's storage file in git-ignored `local/` in plain JSON.
  Phase 1 replaces this with the DPAPI-encrypted vault.
- Not tried yet, but offered by the device: text entry, app list and launch, swipe, artwork.
