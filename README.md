# Tandem

Tandem is a free, open-source Windows app for sending audio and video to Apple TV, HomePod
and other AirPlay 2 speakers and TVs, with smart-home control planned later.

> **Status: pre-alpha, Phase 0 (research spikes).** Nothing to install yet. Pairing and remote
> control of Apple TV, streaming audio to HomePod mini and an AirPlay 2 soundbar, and capturing
> the PC's own audio are proven in spikes, as is fast hardware video encoding on NVIDIA GPUs.
> Screen mirroring was investigated and shelved: it is
> gated by Apple's FairPlay content protection, with no legitimate open-source way to send it
> ([ADR-0006](docs/adr/0006-screen-mirroring-fairplay.md)).
> See the [roadmap](docs/ROADMAP.md).

## Goals

- Discover and pair with Apple TV, HomePod and AirPlay 2 receivers on your network
- Apple TV remote control from your PC
- Stream system audio to any mix of AirPlay speakers and your PC's own speakers, in sync
- Send videos and links to Apple TV
- A clean, Apple-inspired interface that's accessible and works from the system tray

Screen mirroring is **not** planned: it is gated by Apple's FairPlay content protection, with no
legitimate open-source way to send it ([ADR-0006](docs/adr/0006-screen-mirroring-fairplay.md)).

## Contributing

Read [docs/PRIVACY.md](docs/PRIVACY.md) before your first commit, then install the hooks:

```
pip install pre-commit
pre-commit install
python tools/build_denylist.py
```

Architecture decisions are recorded in [docs/adr](docs/adr/).

## Legal

Licensed under GPL-3.0-or-later. This is an independent project, not affiliated with or endorsed
by Apple Inc. Apple TV, HomePod, AirPlay and HomeKit are trademarks of Apple Inc., used here only
to describe compatibility.
