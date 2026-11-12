# Spike I: cast the screen to an Apple TV as live HLS (no FairPlay)

**Result: in progress (paused 2026-11-10).** The PC side works. The TV side hasn't been
measured yet: the Apple TV refused the play request because the spike's old test pairing has
expired, and a new AirPlay PIN pairing needs the maintainer at the TV.

Script: [spikes/spike_i_cast.py](../../spikes/spike_i_cast.py). (Spike G is process loopback
and Spike H is PTP timing, so this one is I. The mirroring add-on test is
[Spike J](spike-j-mirror-addon.md).)

## The pipeline

Desktop duplication (dxcam), then a CPU scale to 1080p, then H.264 (NVENC, falling back to
Media Foundation and then x264), plus the PC's sound from process loopback (ADR-0020) as
AAC. PyAV's HLS muxer writes 1 s MPEG-TS segments in a sliding six-segment playlist, a small
web server on the home network shares the folder under a random path, and the TV is asked to
play the playlist with pyatv's `play_url`, the same request Send to TV uses. No FairPlay
(ADR-0006 addendum).

## Found so far (on the PC, no TV)

| Check | Result |
|---|---|
| Encoder picked | `h264_nvenc` |
| Frame rate, 4K screen scaled to 1080p | 30 fps held, 1 late tick in 8 s |
| Work per frame (scale + encode + mux) | 21 ms median, 23 ms p95 |
| Segments | 1.0 s each, about 1 MB at 8 Mbit/s |
| Sound | AAC 44.1 kHz stereo; silence filled while nothing plays |
| Output check | PyAV reads the playlist back as H.264 + AAC, 5 s for 5 s captured |

Things that went wrong:
- PyAV's audio encoder rejects explicit timestamps on the s16 to AAC path ("non
  monotonically increasing dts"). Leaving `pts` unset works, because sound is paced by sample
  count from the start.
- The HLS muxer's `temp_file` flag fails on Windows. It isn't needed: the playlist only lists
  finished segments.
- Windows maps `.ts` to `video/vnd.dlna.mpeg-tts`, so the server sets `video/mp2t` itself.

## Still to do

1. Pair AirPlay with the reference Apple TV:
   `python spikes/spike_i_cast.py pair`, then write the PIN the maintainer reads off the TV to
   `local/spike-i/pin.txt`.
2. `python spikes/spike_i_cast.py cast --seconds 120`. The script records the TV's
   `/playback-info` replies (position, rate) to estimate lag as stream time minus playback
   position. `--clock` opens an on-screen clock to photograph next to the TV for a
   glass-to-glass check.
3. Try `--start-offset` (EXT-X-START) and shorter segments to get close to the 2 to 3 s
   target. If AVPlayer holds three target durations back no matter what, try LL-HLS.
4. A 10-minute run for stability, CPU and GPU load.
