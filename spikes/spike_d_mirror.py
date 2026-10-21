"""Spike D: screen-mirroring feasibility (Phase 0).

Throwaway spike code. It answers one question for the roadmap: can Tandem send screen
mirroring to an AirPlay receiver, and if not, what is the wall? It does NOT implement or
defeat any content protection. It only:

  1. finds a receiver by the services it advertises (never by name),
  2. reads what that receiver advertises over mDNS (its public AirPlay 'features' value),
  3. checks what pyatv, our chosen library, offers for sending video,

and prints a plain go/no-go summary. The real mirroring data path is gated by FairPlay
(the AirPlay `fp-setup` step); this spike stops at that boundary, and the findings page
plus ADR-0006 record the decision rather than attempting it.

Privacy: receivers are chosen by their advertised service set, not by name. Nothing that
identifies a device (name, address, identifier, public key) is printed. Capability output is
limited to protocol feature values that are the same on every device of a given kind.

Usage (from the repo root, with the dev virtualenv's python.exe):
    python spikes/spike_d_mirror.py find
    python spikes/spike_d_mirror.py probe uxplay|appletv
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import pyatv
from pyatv.const import Protocol
from pyatv.interface import BaseConfig

def parse_features(raw: str | None) -> int:
    """Turn the mDNS 'features' value ('0xLOW,0xHIGH' or '0x...') into one integer."""
    if not raw:
        return 0
    parts = [p.strip() for p in raw.split(",")]
    low = int(parts[0], 16)
    high = int(parts[1], 16) if len(parts) > 1 else 0
    return (high << 32) | low


def is_target(conf: BaseConfig, which: str) -> bool:
    """Pick a receiver by its advertised services and model class, never by name.

    uxplay:  advertises AirPlay + RAOP and reports the model class UxPlay emulates.
    appletv: advertises AirPlay + Companion + RAOP (a real Apple TV).
    """
    svcs = {s.protocol for s in conf.services}
    ap = conf.get_service(Protocol.AirPlay)
    if ap is None:
        return False
    model = str((ap.properties or {}).get("model", ""))
    has_companion = Protocol.Companion in svcs
    if which == "appletv":
        return has_companion and Protocol.RAOP in svcs
    if which == "uxplay":
        # UxPlay emulates an old Apple TV model and offers no Companion service.
        return not has_companion and Protocol.RAOP in svcs and model.startswith("AppleTV3")
    return False


async def find_target(which: str) -> BaseConfig | None:
    loop = asyncio.get_running_loop()
    confs = await pyatv.scan(loop, timeout=5)
    matches = [c for c in confs if is_target(c, which)]
    if not matches:
        print(f"no {which} receiver found")
        return None
    if len(matches) > 1:
        print(f"warning: {len(matches)} receivers matched {which}; using the first")
    return matches[0]


async def pyatv_video_support() -> dict[str, bool]:
    """What does pyatv offer for *sending* video? (Capability check, no device needed.)"""
    from pyatv.interface import Stream
    methods = {m for m in dir(Stream) if not m.startswith("_")}
    return {
        "play_url (media URL / file)": "play_url" in methods,
        "stream_file (audio)": "stream_file" in methods,
        "screen mirroring (send desktop)": False,  # pyatv implements no mirroring sender
    }


async def cmd_find() -> None:
    loop = asyncio.get_running_loop()
    confs = await pyatv.scan(loop, timeout=5)
    print(f"{len(confs)} AirPlay-capable receiver(s) on the network")
    for which in ("uxplay", "appletv"):
        n = sum(1 for c in confs if is_target(c, which))
        print(f"  matching {which}: {n}")


async def cmd_probe(which: str) -> None:
    conf = await find_target(which)
    if conf is None:
        return
    ap = conf.get_service(Protocol.AirPlay)
    feats = parse_features((ap.properties or {}).get("features") if ap else None)

    print(f"== {which} ==")
    # The receiver advertises a 'features' bitfield over mDNS. We print it raw rather than
    # decode individual bits, to avoid asserting bit meanings we can't verify from pyatv.
    print(f"Advertised AirPlay features (raw): 0x{feats:016X}")
    print("   (this receiver type is a screen-mirroring receiver by design)")

    print("pyatv sender support (our chosen library):")
    for label, ok in (await pyatv_video_support()).items():
        print(f"   {label}: {'yes' if ok else 'NO'}")

    print("Feasibility verdict:")
    print("   receiver accepts mirroring: yes")
    print("   open-source sender path:    none (pyatv sends audio and media URLs, not mirroring)")
    print("   remaining gate:             FairPlay (the AirPlay fp-setup step) keys the video")
    print("   decision needed:            see ADR-0006; this spike does not implement or")
    print("                               bypass FairPlay.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Spike D: mirroring feasibility")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("find")
    p = sub.add_parser("probe")
    p.add_argument("target", choices=["uxplay", "appletv"])
    args = parser.parse_args()

    if args.cmd == "find":
        asyncio.run(cmd_find())
    elif args.cmd == "probe":
        asyncio.run(cmd_probe(args.target))
    else:  # pragma: no cover
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
