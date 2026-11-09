# ADR-0022: PTP timing for AirPlay 2 speakers

- Status: Proposed (waiting on the Spike H hardware check)
- Date: 2026-11-09

## Context
pyatv streams to each AirPlay 2 speaker on its own, with NTP timing, and its sync packets tie
each stream's RTP clock to that stream's own start. The speakers then choose their own delay:
by ear the soundbar plays 0.5 to 1 s after the PC and a HomePod mini about 5 s after
(ADR-0011). Line-up (ADR-0018) measures and adds delays, but it is a correction after the
fact, and Phase 5's exit asks for ~20 ms over 30 minutes.

Apple's senders use PTP timing instead: the speakers follow one clock and each sync packet
says which audio sample plays at which clock time. OwnTone (open source) has shipped the same
as a sender since 29.1 (April 2026), with its clock in libairptp (MIT). Every reference
speaker advertises PTP (AirPlay feature bit 41). The maintainer approved the work on
2026-11-09.

## Decision
- **Tandem runs a PTP clock** (`engine/adapters/ptp.py`, ported from libairptp): it binds UDP
  319 and 320, announces itself as a better clock than any Apple device, and sends Sync /
  Follow_Up, Announce and Signaling by unicast to each speaker that streams, answering their
  Delay_Req. It is started for the first PTP stream and stopped after the last
  (`PtpClockShare`). The clock is `time.perf_counter_ns`.
- **pyatv stays the sender.** Two pyatv internals are wrapped next to the existing
  `open_source` hook (`engine/adapters/pyatv_ptp.py`): the session SETUP asks for PTP, names
  Tandem's clock and sends SETPEERS; the sync task sends PTP sync packets (type 0xD7). Only
  streams registered for PTP get them. Streams stay realtime (type 96, PCM).
- **Each stream keeps its own RTP timeline, tied to the shared clock.** A stream's first packet
  plays `PTP_LEAD` (2 s) after it starts; from then RTP time runs at 44.1 kHz of clock time.
  This differs from OwnTone, which sends one shared RTP stream to the whole group; tying each
  stream to the clock gives the same result without replacing pyatv's stream client.
- **Audio is read by time.** The audio hub also feeds a `CaptureTimeline` (`engine/timeline.py`):
  the source by capture time. A PTP stream's packet that plays at time T carries the audio
  captured at `T - PTP_LATENCY` (2.15 s) less the output's line-up offset, so every PTP speaker
  plays the same moment together. The capture timeline follows the sound card's clock drift
  one frame at a time.
- **Fallbacks.** Speakers without PTP, a clock that can't open its ports, and a speaker whose
  PTP setup failed (remembered for the run) use pyatv's NTP timing and the queue, as before.
  Line-up still covers those and the PC's own outputs; a probe on a PTP output goes through a
  timeline of its own, so its measured lag is that of the PTP path.

## Consequences
- PTP speakers play about 2.15 s after the PC, together. That is later than the soundbar
  today but earlier than the HomePod. The PC's own speakers need about that much delay to
  match (line-up sets it).
- Two more pyatv internals are hooked. pyatv is pinned to 0.18; tests check the hook points.
- The Apple TLVs in the PTP messages are copied from iOS captures via OwnTone; a firmware
  change could make a speaker refuse the clock (the fallback covers that).
- The firewall rule is per program, so ports 319/320 need no new rule.
