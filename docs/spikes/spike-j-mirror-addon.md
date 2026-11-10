# Spike J: a third-party mirroring sender as a user-installed add-on

**Result: not run (paused 2026-11-10).** Running the fork's code needs the maintainer's explicit
go-ahead. Nothing from the fork is in this repository, and none of it will be (ADR-0006
addendum).

## What reading the source showed

- **lcd1232/pyatv**, PR #1 "Airplay mirror fairplay" (merged in the fork 2026-11-02), adds
  `pyatv/protocols/airplay/mirror/`: a FairPlay SAP sender handshake in pure Python
  (`fairplay_sap/`), media pair-verify, and a mirroring session that sends H.264 (and
  optionally AAC-ELD) over TCP. pyatv's public API doesn't expose it, so a caller drives the
  classes directly.
- **Pairing:** a one-time PIN registration of an ed25519 "media identity" (`media_pairing.py`),
  separate from pyatv's normal AirPlay pairing. The TV shows a PIN, and its PIN session is
  short-lived.
- **Licence:** the repository is MIT (pyatv's licence). The `fairplay_sap` files carry no
  licence or copyright header of their own. `garble_plain.py` says it computes the same values
  as playfair's `hand_garble.c`, and playfair is GPL-3.0. So whether those files can really
  be MIT is unclear.

## Still to do (only with the maintainer's OK)

Install the fork into a throwaway venv outside the repo, register with the reference Apple TV
(the maintainer reads the PIN off the TV), mirror for a few minutes and measure the lag.
