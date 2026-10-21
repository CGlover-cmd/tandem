# Spike E: screen capture and hardware H.264 encode latency

**Result: go for 1080p, with a known path to 4K60.** From Python, the test laptop captures the
desktop, encodes it on the NVIDIA GPU (NVENC) and decodes it back in about 60 ms, well inside
the 250 ms mirroring target. 1080p30 runs at full rate. 4K60 does not yet: in Python every
frame goes through main memory, which caps a 4K desktop at about 35 fps. Reaching 4K60 means
keeping frames on the GPU from capture to encoder, which FFmpeg supports but PyAV does not
expose.

Screen mirroring stays shelved (ADR-0006). This spike only measures the encoder pipeline on the
PC. It sends nothing to any AirPlay device and has nothing to do with FairPlay.

Script: [spikes/spike_e_encode.py](../../spikes/spike_e_encode.py)

## Setup

- Windows 11 laptop, NVIDIA RTX 3060 Laptop GPU (driver 617), AMD integrated graphics. The
  built-in 3840x2160, 60 Hz display is driven by the NVIDIA GPU.
- Python 3.11, PyAV 18.1 (bundles FFmpeg 8, libavcodec 62), dxcam 0.3.0 (DXGI Desktop
  Duplication), numpy 2.4. All installed into the dev venv; Smart App Control allowed them.
- Low-latency settings throughout: no B-frames, no lookahead, CBR, one packet out per frame in.
  NVENC used preset p1 with the `ull` tune. The default bitrate was 0.1 bit per pixel (6 Mbit/s
  at 1080p30, 50 Mbit/s at 4K60).
- Test content was synthetic moving frames, or the live desktop with a small window animating
  on it. No frames were written to disk.

## Findings

### Encoders available

| Encoder | Opens | Notes |
|---|---|---|
| `h264_nvenc` (NVIDIA) | Yes | Takes BGRA directly; the GPU does the colour conversion |
| `h264_amf` (AMD) | Yes | Takes BGRA directly; slow on this laptop (below) |
| `h264_mf` (Windows Media Foundation) | Yes | Picked the NVIDIA hardware encoder by itself; needs NV12, so the CPU converts first |
| `libx264` (CPU) | Yes | Software baseline; needs NV12 |
| `h264_qsv` (Intel) | No | No Intel GPU |

### Capture (dxcam, desktop duplication)

| Check | Result | Notes |
|---|---|---|
| 4K desktop while it changes | Pass | 59.7 fps, matching the 60 Hz display |
| Copy each frame to main memory | 8.4 ms median, 13.9 ms p95 | 33 MB per 4K frame |
| Screen change seen by capture | 28 ms median, 41 ms p95 | Includes the window drawing and Windows compositing at 60 Hz (up to two display frames) |
| CPU | 1 core | The spike polls in a busy loop; an engine would wait on the next frame instead |
| FFmpeg `ddagrab` instead of dxcam | 8.0 ms per frame to main memory | Same speed; ddagrab into NVENC through memory reached 38 fps at 4K (encode 17.7 ms) |

### Encode latency (frame in to packet out)

Paced in real time; "fps" is the rate achieved against the target.

| Encoder | Source | Target | Achieved | Encode median / p95 | CPU |
|---|---|---|---|---|---|
| NVENC | synthetic 1080p | 30 fps | 30 fps | 5.9 / 12.5 ms | 17% |
| NVENC | synthetic 1080p | 60 fps | 60 fps | 5.4 / 6.6 ms | 10% |
| NVENC | synthetic 1080p, unpaced | max | 117 fps | 5.2 / 5.9 ms | 57% |
| NVENC | synthetic 4K | 60 fps | 52 fps | 18.8 / 20.6 ms | 27% |
| NVENC | live 4K desktop | 60 fps | 35 fps | 17.5 / 19.0 ms | 57% |
| NVENC | live 4K desktop scaled to 1080p | 30 fps | 30 fps | 5.4 / 7.9 ms (+14 ms CPU scaling) | 183% |
| NVENC | live 4K desktop scaled to 1080p | 60 fps | 31 fps | 5.4 / 9.5 ms (+14 ms CPU scaling) | 228% |
| Media Foundation | synthetic 1080p | 30 fps | 30 fps | 7.7 / 15.2 ms (+9.7 ms CPU to NV12) | 89% |
| x264 ultrafast | synthetic 1080p | 30 fps | 30 fps | 2.6 / 3.0 ms (+8.1 ms CPU to NV12) | 109% |
| x264 ultrafast | synthetic 1080p | 60 fps | 60 fps | 2.7 / 3.5 ms (+7.7 ms CPU to NV12) | 230% |
| AMF | synthetic 1080p | 30 fps | 30 fps | 54 / 55 ms | 74% |
| AMF | synthetic 1080p | 60 fps | 40 fps | 46 / 49 ms | 100% |
| AMF | synthetic 4K | 60 fps | 9 fps | 193 / 205 ms | 99% |

The NVIDIA driver's own figure for time inside the encoder (from `nvidia-smi`) was about 2.5 ms
at 1080p and 9 to 10 ms at 4K. The rest of the NVENC time is the upload from main memory into
the encoder.

### Screen change to decoded picture, all on the PC

A patch in a window turned red or blue. Each trial measured the time until capture saw the new
colour, the encode, and a software decode back to a picture. That last step stands in for the
receiver. The decoded colour was correct in all 90 trials.

| Pipeline | Capture | Scale + encode | Decode | Total median / p95 |
|---|---|---|---|---|
| NVENC, native 4K | 28 ms | 19 ms | 8.7 ms | 56 / 70 ms |
| NVENC, 4K scaled to 1080p | 37 ms | 19 ms | 3.7 ms | 59 / 62 ms |
| x264, 4K scaled to 1080p | 37 ms | 13 ms | 1.8 ms | 52 / 67 ms |

Network transfer, the receiver's buffer and its display are not included.

### Things that went wrong

| Issue | What happened | Workaround |
|---|---|---|
| PyAV `VideoFrame.from_ndarray` is slow | It takes 36 ms to copy a 4K frame (numpy itself takes 5.5 ms) and capped 4K at 14 to 19 fps | `VideoFrame.from_numpy_buffer` wraps the array without copying (0.1 ms) |
| dxcam crashes on release | `release()` and comtypes' COM cleanup crash with an access violation | The spike never releases the camera and ends with `os._exit` |
| GPU-only encode not reachable from PyAV | FFmpeg's `ddagrab` filter does work through PyAV and returns D3D11 GPU frames, and NVENC accepts D3D11 input. But PyAV gives no way to hand the encoder the frames' GPU context, so opening it fails | Not solved in the spike (see below) |
| GPU scaling | FFmpeg's `scale_d3d11` filter could not create its output texture from `ddagrab` frames in this build | CPU scaling (libswscale), 14 ms per frame from 4K to 1080p |

## What this means if mirroring is ever reopened (Phase 7)

- **The encoder is not the bottleneck.** NVENC itself needs about 2.5 ms per 1080p frame and
  10 ms per 4K frame. Total time on the PC is about 60 ms, which leaves about 190 ms of the
  250 ms target for the network and the receiver.
- **1080p30 from Python is ready.** Capture, CPU scaling and NVENC hold 30 fps with room to
  spare. For 1080p60 the steps need to run in parallel, or the scaling needs to move to the GPU.
- **4K60 needs a GPU-only path.** That means desktop duplication (or `ddagrab`) feeding a D3D11
  texture straight into NVENC, with no trip through main memory. FFmpeg already does this, but
  PyAV cannot connect the two. This answers the open question in ADR-0001: real-time 4K video
  would need a small native helper or direct calls into the bundled FFmpeg libraries.
  Everything else can stay in Python.
- **Encoder choice:** NVENC first. Media Foundation is a good fallback because it ships with
  Windows and finds the GPU's encoder by itself. x264 ultrafast is the fallback for PCs with no
  hardware encoder: it is fast but uses one to two CPU cores. AMF was far slower on this laptop
  (46 to 193 ms per frame), probably because the AMD integrated GPU doesn't drive the display
  here. Untested on a PC where AMD is the main GPU.
- **Laptops whose display runs on the integrated GPU** capture on that GPU. On those, frames
  cross to NVENC through main memory anyway, so the CPU path measured here is the general
  case. The GPU-only path only helps when the display and the encoder are on the same GPU.

## Not tried

- Capturing a single window (Windows Graphics Capture), and capturing a second display
- Running capture, scaling and encoding in parallel threads
- HEVC, and 10-bit
- Intra-refresh instead of periodic keyframes (smaller bursts on the network)
- Windows 10 22H2
- Anything over the network, or to a receiver
