# ADR-0015: PC speakers as outputs, and sending media to Apple TV

- Status: Accepted (recorded 2026-11-04 from the code; the session that wrote it crashed first)
- Date: 2026-10-27

## Context
Phase 5 lets the PC's own sound devices play next to AirPlay outputs, and Phase 7 sends a video
file or link to an Apple TV. The code for both landed before its ADR was written, and modules
already cite this record.

## Decision
**Local outputs.** Each playback device Windows offers (speakers, headphones, a USB DAC) is an
output in the audio hub, played through miniaudio. Its stream is delayed by a per-output buffer,
so it can line up with AirPlay receivers, which buffer for a second or more. While the source
is the PC's own audio (loopback), the device that loopback captures is never offered, because
it would feed the sound back into itself. In-sync local playback therefore needs a virtual
cable as the Windows default, as ADR-0005 planned.

**Media send.** The Apple TV plays a URL itself, using AirPlay's "play this URL", not mirroring,
so no FairPlay is involved (ADR-0006). A link is passed as is. For a file on this PC, Tandem
starts a small aiohttp server on a random port and shares only that file, under a fresh
random path (`secrets.token_urlsafe`) per file. File paths and links are never logged.

## Consequences
- The server listens on all interfaces, so anyone on the home network who learns a path can
  fetch that file. Shared paths stay valid until the server stops; stopping it when sending
  ends is a Phase 9 hardening item.
- Windows Firewall will ask about the inbound port; the Phase 9 installer should add a rule.
- Local-output delay and AirPlay latency must match to within ~20 ms (Phase 5 exit), which
  depends on finding the HomePod mini's ~5 s lag first (Phase 4 open item).
- The local playback sink needs sound hardware, so it's excluded from coverage and checked by hand.
