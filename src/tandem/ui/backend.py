"""What the UI needs from the engine.

This is the UI's side of the service API. The engine adapter (and `DemoBackend` until then)
implements `Backend`. The enums mirror the engine's `DeviceKind` and `ConnectionState`
values so the adapter is a straight mapping.

Device names and ids are private (docs/PRIVACY.md). The UI shows names on screen but never
logs them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class DeviceKind(Enum):
    APPLE_TV = "apple_tv"
    HOMEPOD = "homepod"
    RECEIVER = "receiver"  # third-party AirPlay 2 speaker, soundbar or TV
    OTHER = "other"


class LinkState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    WAITING = "waiting"  # waiting to retry after a failed attempt or a dropped connection
    FAILED = "failed"  # gave up retrying


@dataclass(frozen=True, slots=True)
class DeviceSnapshot:
    """Everything the UI shows about one device, at one moment."""

    id: str
    name: str
    kind: DeviceKind
    state: LinkState = LinkState.DISCONNECTED
    needs_pairing: bool = False
    """The device must be paired (PIN) before it can connect."""
    retry_in: float | None = None
    """Seconds until the next attempt, when `state` is WAITING."""


class Theme(Enum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


NEUTRAL_BACKGROUNDS = ("mist", "sand", "slate")
GRADIENT_BACKGROUNDS = ("sky", "dusk", "meadow", "sunrise", "aurora")
BACKGROUNDS = NEUTRAL_BACKGROUNDS + GRADIENT_BACKGROUNDS
"""Window backgrounds the user can pick in Settings. The front end defines their colours."""


@dataclass(frozen=True, slots=True)
class Appearance:
    theme: Theme = Theme.SYSTEM
    background: str = "mist"

    def __post_init__(self) -> None:
        if self.background not in BACKGROUNDS:
            raise ValueError("unknown background")


@dataclass(frozen=True, slots=True)
class DeviceUpdated:
    device: DeviceSnapshot


@dataclass(frozen=True, slots=True)
class DeviceRemoved:
    device_id: str


@dataclass(frozen=True, slots=True)
class DiscoveryChanged:
    active: bool


@dataclass(frozen=True, slots=True)
class AppearanceChanged:
    appearance: Appearance


BackendEvent = DeviceUpdated | DeviceRemoved | DiscoveryChanged | AppearanceChanged
Listener = Callable[[BackendEvent], None]
Unsubscribe = Callable[[], None]


class PairingError(Exception):
    """Pairing did not succeed. `str(error)` is safe to show the user; it holds no private data."""


class WrongPinError(PairingError):
    """The PIN did not match; the user may try again."""


class PairingFlow(Protocol):
    """One pairing attempt. The device shows a PIN; the user types it into Tandem.

    Some devices ask for more than one: an Apple TV pairs remote control and AirPlay
    separately, and shows a new PIN for each.
    """

    @property
    def steps(self) -> int:
        """How many PINs the user will enter in all (at least 1)."""
        ...

    async def submit_pin(self, pin: str) -> bool:
        """Check the PIN the device is showing now.

        Returns True if the device now shows the next PIN, False when pairing is complete.
        Raises `WrongPinError` (the device shows a fresh PIN to retry) or `PairingError`.
        """
        ...

    async def cancel(self) -> None: ...


class Backend(Protocol):
    def subscribe(self, listener: Listener) -> Unsubscribe:
        """Call `listener` on the asyncio loop thread for every change."""
        ...

    def devices(self) -> list[DeviceSnapshot]: ...

    async def start(self) -> None:
        """Start discovery. Devices arrive through `subscribe`."""
        ...

    async def stop(self) -> None: ...

    async def connect(self, device_id: str) -> None: ...

    async def disconnect(self, device_id: str) -> None: ...

    async def begin_pairing(self, device_id: str) -> PairingFlow:
        """Ask the device to show a PIN. Raises `PairingError` if it can't."""
        ...

    def appearance(self) -> Appearance: ...

    async def set_appearance(self, appearance: Appearance) -> None:
        """Save the user's choice and publish `AppearanceChanged`."""
        ...
