"""Plain data types shared by the engine and the UI. No protocol library types leak out."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DeviceKind(Enum):
    """What sort of receiver a device is, used for icons and grouping."""

    APPLE_TV = "apple_tv"
    HOMEPOD = "homepod"
    RECEIVER = "receiver"  # third-party AirPlay 2 speaker, soundbar or TV
    OTHER = "other"


class Service(Enum):
    """Network protocols a device offers."""

    AIRPLAY = "airplay"
    RAOP = "raop"  # AirPlay audio
    COMPANION = "companion"  # Apple TV remote control
    MRP = "mrp"
    DMAP = "dmap"


@dataclass(frozen=True, slots=True)
class Device:
    """A receiver seen on the network.

    `name`, `address` and `id` are private (docs/PRIVACY.md): they are redacted in logs and
    must never appear in committed files.
    """

    id: str
    name: str
    address: str
    kind: DeviceKind
    model: str
    services: frozenset[Service]
    paired: frozenset[Service] = field(default=frozenset[Service]())
    """Services with stored pairing credentials."""
    needs_pairing: frozenset[Service] = field(default=frozenset[Service]())
    """Services the device only allows after pairing, not paired yet."""

    @property
    def can_play_audio(self) -> bool:
        return Service.RAOP in self.services or Service.AIRPLAY in self.services

    @property
    def can_remote_control(self) -> bool:
        return Service.COMPANION in self.services or Service.MRP in self.services
