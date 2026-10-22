# Music spike 1: reading and controlling media sessions

**Result: go for the Apple Music app; the Spotify app and a browser are still to check.**
Windows' media controls (`Windows.Media.Control`, "GSMTC") give Python everything the
now-playing bar needs from the Apple Music app: the app's id, playback status, which controls
it allows, the timeline, whether there's a title, artist and artwork, and change events, so
Tandem never has to poll. Play, pause and toggle worked every time and each raised an event
within a second.

Script: [spikes/spike_music_media_sessions.py](../../spikes/spike_music_media_sessions.py)
(`list`, `watch`, `control`). It prints yes/no flags instead of titles and artists, so its
output is safe to paste.

## Setup

- Windows 11 laptop, Python 3.11, pywinrt 3.2.1: `winrt-Windows.Media.Control`,
  `winrt-Windows.Foundation`, `winrt-Windows.Foundation.Collections` and
  `winrt-Windows.Storage.Streams` (now in the `dev` extra). They install from wheels and load
  with Smart App Control on.
- Apps installed: Apple Music (Microsoft Store app) and Spotify (Microsoft Store app). Only the
  Apple Music app was playing during the test. Spotify wasn't running, and we didn't start it,
  so as not to touch the maintainer's Spotify account. No browser tab was playing.
- The Apple Music app was playing a long continuous item (about an hour, with next and
  previous turned off by the app), so skipping couldn't be exercised.

## Findings

| Check | Apple Music app | Notes |
|---|---|---|
| Session listed, with app id | Pass | `AppleInc.AppleMusicWin_nzyj5cx40ttqa!App`; it was also the "current" session |
| Playback status | Pass | `playing` / `paused`, matching the app |
| Allowed controls | Pass | pause and toggle on; play off while playing; next, previous, seek, shuffle and repeat off for this item |
| Timeline (position, end, seekable range) | Pass | Position moved in step with playback; end about 1 h |
| Title, artist, album artist | Present | Album and track number empty for this item |
| Artwork (thumbnail) | Pass | JPEG, about 120 KB, readable as a stream |
| `pause`, `play` | Pass | Accepted; status changed within 1.5 s |
| `toggle` (twice) | Pass | playing → paused → playing |
| `next` while the app had it turned off | Accepted, did nothing | The call returned "accepted" but no track change or media event followed |
| Change events over 30 s | Pass | 4 playback-info events (one per pause or play) and about 3 timeline events a second while playing, none while paused; no media-properties event, as the item didn't change |

## What this means for Phase 6

- The now-playing bar can be event-driven: subscribe to the session manager's
  sessions-changed and current-session-changed events, and to each session's
  media-properties, playback-info and timeline events. Events arrive on a WinRT thread pool
  thread; hand them to the engine's loop with `call_soon_threadsafe`.
- Timeline events are frequent (about 3 a second from Apple Music). The engine should pass on
  position at a lower rate and let the UI interpolate from the last position and its time.
- A command's "accepted" result doesn't mean it did anything. Show only the controls the
  session says are enabled, and confirm by the next event rather than by the return value.
- Titles and artists reach the engine, so they must go through `Redactor` in logs and
  diagnostics like device names (ADR-0007, ADR-0012).
- `playback_type` (music, video, image) needs the `winrt-Windows.Media` package too; add it
  when the adapter wants it.

## Still to check

The phase's exit needs three apps. To finish this spike, with something playing in each:

```
python spikes/spike_music_media_sessions.py list
python spikes/spike_music_media_sessions.py watch --seconds 30
python spikes/spike_music_media_sessions.py control --app Spotify --action next
```

- The Spotify app: next and previous on a playlist, and whether artwork is present.
- A browser tab (Edge or Firefox) playing audio.
