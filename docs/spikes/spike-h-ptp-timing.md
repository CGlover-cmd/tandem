# Spike H: PTP timing for AirPlay 2 speakers

Status: research done and code written (2026-11-09); hardware check waiting on the maintainer.
Decision record: [ADR-0022](../adr/0022-ptp-timing-for-airplay-2.md).

## Question
Can Tandem make AirPlay 2 speakers follow its own clock, as Apple's senders do, so they play
together without per-speaker delays?

## Research
No official AirPlay 2 specification is public. The best references:

- **OwnTone** (GPL-2.0-or-later) has shipped an AirPlay 2 sender with PTP timing since 29.1
  (April 2026): "Samsung and Sonos Era speakers via support for Airplay 2 PTP timing" and
  shairport-sync's AirPlay 2 mode. It uses PTP for every speaker that advertises it. Its clock
  is **libairptp** (MIT), "designed to always become master clock, which a sender ... needs".
- **shairport-sync + nqptp** show the receiver side: the speaker follows the sender's clock.

How a sender does it (OwnTone, matching iOS where its code says so):
1. A PTP clock on UDP 319 (event) and 320 (general), unicast to each speaker: Announce every
   1 s (priority1 128, clock class 6, so it beats Apple devices at 248), Sync + Follow_Up
   (two-step) every 125 ms, Signaling every 1 s, and a Delay_Resp to each Delay_Req.
2. Session SETUP with `timingProtocol: PTP`, `timingPeerInfo` (`ID`, `ClockID` as a signed
   64-bit integer, `Addresses`, `DeviceType` 0, `SupportsClockPortMatchingOverride` false), a
   one-entry `timingPeerList`, a `groupUUID` and `groupContainsGroupLeader` false. The reply's
   `timingPeerInfo` names the speaker's PTP addresses.
3. SETPEERS (content type `/peer-list-changed`, a plist array of the speaker's and the PC's
   addresses).
4. Realtime audio (type 96) as before.
5. Sync packets about once a second: 28 bytes, payload type 0xD7: the RTP time playing now, the
   clock time in nanoseconds, the next RTP time less 11025, and the clock id.

All reference speakers advertise PTP (feature bit 41): the soundbar (JBL Bar 5.1), both HomePod
minis and the Apple TV (read-only mDNS check from the maintainer's PC).

## Why the current timing can't line speakers up
pyatv's NTP sync packets say each stream's first packet plays 1.5 s after it is sent. If the
speakers followed that, they would already play together. By ear the soundbar plays 0.5 to 1 s
behind and the HomePod mini about 5 s: they pick their own delay in AirPlay 2 mode.

## What was built
See ADR-0022: `engine/adapters/ptp.py` (the clock), `engine/adapters/pyatv_ptp.py` (the pyatv
hooks), `engine/timeline.py` (audio by capture time) and the PTP path in `PyatvAudioSink`.
Windows: `time.monotonic` ticks every 15.6 ms on Python 3.11, so all timing uses
`time.perf_counter_ns`. Binding 319/320 needs no administrator rights on Windows, and the
installer's firewall rule is per program, so it covers them.

## Hardware check
`spikes/spike_h_ptp.py`, under the installed app's Python (`spikes/run_under_app.py`):
- `find`: models and whether each advertises PTP.
- `compare`: a click track whose beeps fall on each whole second of the PTP clock (cycling
  through four notes), 30 s with PTP timing then 30 s with NTP timing, to the soundbar and a
  HomePod mini at once. Pass: with PTP, one beep per second, same note on both; and the
  speakers send Delay_Req (they follow the clock).
- `engine`: the same beeps as a file through Tandem's player and audio hub, which picks PTP
  for speakers that offer it.

Results: to come.
