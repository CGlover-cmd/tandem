# ADR-0001: Python engine built on pyatv

- Status: Accepted
- Date: 2026-10-20

## Context
The app must discover, pair with, control and stream to Apple TV, HomePod and third-party
AirPlay 2 receivers. Reimplementing these reverse-engineered protocols from scratch would take
months and would trail Apple's firmware changes.

## Decision
Write the engine in Python (3.11+) on asyncio, using pyatv for discovery, pairing, Companion
remote control and AirPlay/RAOP audio. Heavy media work (encoding, resampling) runs in native
libraries through PyAV/FFmpeg, so Python is never in the per-sample or per-pixel hot path.
Protocol gaps are filled in our own adapters and, where useful, contributed upstream.

## Consequences
- Fast start, mature protocol coverage, an active upstream community.
- One language across engine and UI lowers the bar for contributors.
- Real-time video (Phase 7) may need a native helper if Spike E shows Python overhead matters.
- Tooling: ruff, pyright, pytest; virtual environment kept outside synced folders.
