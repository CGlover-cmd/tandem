# ADR-0011: System audio pipeline

- Status: Accepted
- Date: 2026-10-21

## Context
Phase 4 streams the PC's own audio to one AirPlay output. Spike C proved WASAPI loopback
capture through miniaudio, and Spikes B and F proved pyatv's sender with files. Three findings
shaped the design:
- pyatv's `stream_file` takes a file, URL or byte stream and decodes it with miniaudio. Its
  decoder can't open an endless live stream (an unbounded WAV fails to initialise), so live audio
  can't go in that way.
- pyatv sends one packet (352 frames, 8 ms) at a time in real time and asks the source for each.
  A source that waits for audio slows the whole stream down: the first Pi run delivered 0.75 s of
  audio in 18 s.
- WASAPI loopback delivers nothing at all while nothing is playing (re-checked in Phase 4; Spike
  C's "blocks keep arriving" was measured with sound playing).

## Decision
- **Capture** (`adapters/loopback.py`): one WASAPI loopback capture of the default output,
  converted by miniaudio to 44.1 kHz, 16-bit stereo, the AirPlay audio format. It's shared by all
  outputs and runs only while at least one output streams.
- **Jitter buffer per output** (`engine/audio.py`, `PcmBuffer`): the capture thread pushes into
  every output's buffer. The sender's reads never wait. They return audio once 100 ms has built
  up, and silence when there isn't enough. After an underrun the buffer builds up again. Over
  1 s behind, the oldest audio is dropped, so a stream stays live rather than drifting late.
- **Into pyatv** (`adapters/pyatv_audio.py`): a `LivePcmSource` (a pyatv `AudioSource`) reads
  the buffer. pyatv's internal `open_source` is wrapped once so this source passes through
  untouched, while every other input still goes to pyatv's own decoder. pyatv is pinned to a
  minor version, and a test checks the hook point still exists. Samples go in big-endian, as
  pyatv's own sources hand them over (sent little-endian, they arrive as noise).
- **Resilience** (`engine/audio_hub.py`): when the connection drops, the stream stops at once.
  It restarts with a fresh, empty buffer when the session reconnects. A stream that fails while
  the connection stays up retries with backoff. A user disconnect stops it.

## Consequences
- No decode step and no extra latency on the sending side. The buffer adds about 100 ms on top
  of the receiver's own buffer.
- The capture clock and the sender's clock drift slowly apart. Phase 4 lives with it: a rare
  re-prime gap or a dropped slice. Phase 5 (several outputs in sync) needs real drift
  correction.
- Loopback follows the Windows volume and mute on this PC (Spike C, ADR-0005). Phase 4 doesn't
  compensate yet.
- The hook depends on a pyatv internal. Moving the pyatv pin means re-checking it. The
  alternative, a pyatv change to accept an `AudioSource`, is worth offering upstream.
