# Spike G: shared-clock (PTP) timing for AirPlay 2 speakers

Status: research done (2026-11-09); prototype written (`spikes/spike_g_ptp.py`), hardware run next.

## Question
Can Tandem play to several AirPlay 2 speakers in sync the way Apple's senders do, with the
speakers following one clock, instead of streaming to each speaker on its own and covering the
difference with per-speaker delays?

## Why it matters
Today pyatv streams to each speaker separately ("realtime" stream, NTP timing). Each stream has
its own timeline and each speaker adds its own latency, so a HomePod mini plays audibly behind
the JBL soundbar (heard in the music library check, 2026-11-09). The line-up feature measures
and adds delays, but that is a correction after the fact; the speakers themselves aren't locked
together.

## What we found
No official AirPlay 2 specification is public. The best references:

- **OwnTone** (owntone-server, GPL-2.0-or-later) is an open-source AirPlay 2 sender that keeps
  several speakers in sync. Its PTP part, **libairptp**, is a separate MIT-licensed library
  ("implements the Precision Time Protocol in the way an AirPlay 2 sender ... needs. It is not
  an actual PTP clock"). Both licences allow us to port the approach into Tandem (GPL-3) with
  credit.
- **shairport-sync + nqptp** (the receiver side) confirm the shape from the other end: the
  receiver follows the PTP clock of the sender that connected.

How a sender does it (OwnTone, matching iOS where the code says so):

1. **A PTP clock on the PC.** The sender binds UDP 319 (event) and 320 (general) and announces
   itself as the best clock, unicast to each speaker: Announce every 1 s, Sync + Follow_Up
   (two-step) every 125 ms, a Signaling message every 1 s, and a Delay_Resp to each Delay_Req
   the speaker sends. Domain 0; clock id = 0xFFFF followed by 6 random bytes. A speaker that
   sends nothing for 15 s is dropped. Timestamps come from a monotonic clock.
2. **Session SETUP** says `timingProtocol: PTP` and describes the clock: `timingPeerInfo`
   (`ID`, `ClockID` as a signed 64-bit integer, `Addresses`, `DeviceType` 0,
   `SupportsClockPortMatchingOverride` false), a one-entry `timingPeerList`, a random
   `groupUUID`, `groupContainsGroupLeader` false. The speaker's reply lists its own addresses;
   the sender adds the speaker to its PTP peers.
3. **SETPEERS** (a plist array: the speaker's address and the PC's addresses) before playback.
4. **One shared timeline.** All speakers in a group share one RTP stream position and packet
   sequence; the same encrypted packets go to each. The stream SETUP is unchanged
   (realtime type 0x60; OwnTone sends ALAC, pyatv sends PCM; latencyMin 11025 samples).
5. **Sync packets** on each speaker's control port about once a second: 28 bytes, payload type
   0xD7 ("time announce"), first one marked 0x90: the current RTP time, the clock time in
   nanoseconds, the RTP time minus 11025, and the PTP clock id. (NTP speakers get the older
   20-byte 0xD4 packet.) OwnTone doesn't use SETRATEANCHORTIME.

Our speakers (read-only mDNS check, `spikes/ptp_features.py`): the JBL Bar 5.1, the HomePod
minis and the Apple TV all advertise PTP (feature bit 41) and buffered audio (bit 40).

## What it takes in Tandem
- A small PTP clock in the engine (asyncio, two UDP sockets), ported from libairptp.
- Our own AirPlay 2 stream client for groups: pyatv's pieces (pairing/verify, RTSP, ChaCha20
  packet encryption) with our SETUP, SETPEERS, one shared timeline and the 0xD7 sync packets.
  pyatv has no multi-speaker or PTP support (its issue #2591 asks for it).
- Firewall: inbound UDP 319/320 from the speakers (Delay_Req). The installer's rule for
  Tandem's own program already covers any port on Private/Domain networks.

## Risks
- **Timestamp precision on Windows.** Python 3.11's `time.monotonic()` ticks every ~15.6 ms
  on Windows; use `time.perf_counter_ns()` (QueryPerformanceCounter, sub-microsecond) for PTP
  and sync timestamps. Python adds jitter of a fraction of a millisecond, which the speakers'
  PTP filters should absorb; to be measured.
- **Ports 319/320 in use** (another PTP service). Windows' own time service uses 123 and its
  PTP provider is off by default. To be checked on first run.
- **Unknown Apple TLVs** are copied byte for byte from iOS captures (via OwnTone); a speaker
  could reject the clock if they matter. OwnTone works with HomePods today.
- **No public spec**: details can change with speaker firmware.

## Next: hardware prototype (spike G, part 2)
A throwaway script that runs the PTP clock and streams the click test on one shared timeline to
the soundbar and a HomePod mini. Pass: no audible gap between them (and a microphone line-up
measurement within a few milliseconds), for 10 minutes without drift. If it passes, an ADR and
the engine work; if not, the per-speaker delays stay.
