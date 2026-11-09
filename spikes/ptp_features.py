"""Which AirPlay speakers advertise PTP timing (feature bit 41) and buffered audio (bit 40)?

Read-only mDNS scan. Prints model and the two bits only: no names, addresses or ids.
Usage: python spikes/ptp_features.py
"""

from __future__ import annotations

import asyncio
import os
import sys

import pyatv
from pyatv.const import Protocol

BITS = {40: "buffered audio", 41: "PTP", 38: "unified media control", 52: "SETPEERS extended"}


def features(raw: str) -> int:
    """AirPlay features: "0xLOW,0xHIGH" (two 32-bit halves) or one hex number."""
    parts = [int(p, 16) for p in raw.split(",") if p]
    if len(parts) == 2:
        return parts[0] | (parts[1] << 32)
    return parts[0] if parts else 0


async def main() -> None:
    confs = await pyatv.scan(asyncio.get_running_loop(), timeout=5)
    rows = []
    for conf in confs:
        model = str(conf.device_info.raw_model or conf.device_info.model)
        for protocol in (Protocol.AirPlay, Protocol.RAOP):
            service = conf.get_service(protocol)
            if service is None:
                continue
            raw = service.properties.get("features") or service.properties.get("ft") or ""
            if not raw:
                continue
            value = features(raw)
            bits = ", ".join(
                f"{name}={'yes' if value >> bit & 1 else 'no'}" for bit, name in BITS.items()
            )
            rows.append(f"{model!r:22} {protocol.name:7} {bits}")
            break
    for row in sorted(set(rows)):
        print(row)


if __name__ == "__main__":
    asyncio.run(main())
    sys.stdout.flush()
    os._exit(0)
