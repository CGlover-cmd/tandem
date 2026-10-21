# Spike F: the Raspberry Pi 3 as an audio test receiver

**Result: go, in classic AirPlay mode.** shairport-sync on the test Pi receives pyatv's audio
stream and writes it to a file bit for bit, so later phases can check audio automatically with
no one listening. It works over classic AirPlay (AirPlay 1) only: pyatv's AirPlay 2 sender asks
for NTP timing, and shairport-sync's AirPlay 2 mode only supports PTP timing, so they can't
talk. The AirPlay 2 path that the HomePods and soundbar use stays a hardware check.

Script: [spikes/spike_f_pi_receiver.py](../../spikes/spike_f_pi_receiver.py)

## Setup

- Raspberry Pi 3 (wired Ethernet), Debian 13. Debian's packaged shairport-sync (4.3.7) is built
  without AirPlay 2, so shairport-sync 5.6 was built from source with AirPlay 2 support, plus
  nqptp 1.2.9 (its PTP clock helper). Both run on demand, not at boot.
- shairport-sync plays through its `stdout` back end into a raw PCM file instead of a sound
  card, pinned to 44.1 kHz/16-bit stereo to match the source. (Left on its defaults, an AirPlay 2
  build writes 48 kHz/32-bit, even for classic sessions.)
- Windows 11 laptop on Wi-Fi, Python 3.11, pyatv 0.18.0
- Tone: 440 Hz sine, 44.1 kHz/16-bit stereo, peak at half of full scale, same as Spike B,
  sent with `stream.stream_file` (RAOP)
- The script copies the file back and checks it sample by sample: tone length, pitch, gaps over
  1 ms, glitches (jumps a clean sine can't make), noise after removing a fitted sine, and level

## Findings

| Check | Result | Notes |
|---|---|---|
| Found by kind, not name | Pass | Advertises model `ShairportSync`; no pairing needed |
| AirPlay 2 mode, pyatv in AirPlay 2 | **Fail** | `SETUP` refused (501): the receiver logs that it can't handle NTP streams |
| AirPlay 2 mode, pyatv forced to AirPlay 1 | **Fail** | No answer to `ANNOUNCE`; this mode doesn't take classic sessions |
| Classic mode, 5 s tone, volume 100% | Pass | Length, pitch and samples match the source exactly (noise at the 16-bit floor, ~90 dB down) |
| Classic mode, 2 min tone, volume 100% | Pass | No gaps, no glitches, bit-exact over Wi-Fi |
| Stream call, total (5 s tone) | 6.6 s | 1.6 s over the tone length, against 2.5 to 4.7 s on the real speakers (Spike B) |

**Volume.** pyatv's level changes the output as follows on this receiver; the curve is
shairport-sync's own and real speakers will differ:

| pyatv volume | 100% | 75% | 50% | 30% | 10% |
|---|---|---|---|---|---|
| Level vs source | 0 dB | −12 dB | −29 dB | −46 dB | below −54 dB (reads as silence) |

## What this means for later phases

- **Phase 4 can test automatically.** A test can stream known audio to the Pi and check the
  result for gaps, glitches and level without anyone listening. Use volume 100% when checking
  samples exactly: turning the volume down rounds the 16-bit samples and adds noise.
- **The Pi only covers classic AirPlay.** pyatv sends AirPlay 2 with NTP timing (hard-coded in
  pyatv 0.18), and shairport-sync's AirPlay 2 mode only accepts PTP. Real HomePods and the
  soundbar accept pyatv's AirPlay 2 stream (Spike B), so the shipped app is unaffected, but that
  path can only be checked on the real speakers. Added to the risk register.
- **Multi-room sync (Phase 5).** AirPlay 2 speakers normally sync to a shared PTP clock; pyatv
  uses NTP per stream. Phase 5 should check early whether NTP-timed streams to several speakers
  can hold the ~20 ms target, or whether PTP is needed.
- **Classify devices by service and model string (Phase 1).** Spike B picked the soundbar as
  "the one non-Apple device that takes audio streams". With the Pi receiver running there are
  two, so the device registry must not rely on that rule. Stop the Pi receiver when running the
  hardware spikes.
- **One receiver at a time on the Pi.** UxPlay (Spike D) and shairport-sync both use port 7000,
  so the script refuses to start while UxPlay is running.

## Not covered here

- A live stream from WASAPI loopback (Phase 4); this spike sent a file.
- Latency from send to play-out; the stdout back end doesn't keep play-out time.
- Several receivers at once and their sync (Phase 5).
- Metadata and artwork, and volume changes mid-stream.
