"""Speakers added by address, for networks that hide them from discovery.

Some routers, mesh Wi-Fi systems and guest networks drop the multicast messages that discovery
uses, so a speaker that plays fine never shows up. The user can then type its address (shown
in the Home app or the router) and Tandem asks that address directly on every scan. AirParrot
calls the same fallback "Quick Connect".

Addresses are private (docs/PRIVACY.md): kept in the user's own folder, shown in the window,
never logged and never put in a diagnostics bundle.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import tempfile
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

MAX_ADDRESSES = 20


class AddressError(ValueError):
    """Not an address Tandem can ask. `reason` says why, as a code."""

    INVALID = "invalid"  # not an IPv4 address
    NOT_LOCAL = "not_local"  # public internet, loopback or multicast: never a home speaker
    TOO_MANY = "too_many"
    NO_ANSWER = "no_answer"  # nothing at that address answered as an AirPlay device

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def normalize(text: str) -> str:
    """The address in standard form. Raises `AddressError`.

    Only private IPv4 addresses (home networks) are taken: discovery's unicast queries go to
    IPv4, and anything else would be a typo or a request that leaves the home network.
    """
    try:
        address = ipaddress.IPv4Address(text.strip())
    except ValueError:
        raise AddressError(AddressError.INVALID) from None
    if not address.is_private or address.is_loopback or address.is_multicast:
        raise AddressError(AddressError.NOT_LOCAL)
    if address.is_unspecified or address.is_reserved:
        raise AddressError(AddressError.NOT_LOCAL)
    return str(address)


class AddressStore:
    """The saved addresses, in the order they were added. `path=None` keeps them in memory."""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._addresses: list[str] = []

    def addresses(self) -> list[str]:
        return list(self._addresses)

    def load(self) -> None:
        if self._path is None:
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            _LOGGER.warning("Saved addresses unreadable (%s); starting fresh", type(exc).__name__)
            return
        if not isinstance(data, list):
            return
        for item in data[:MAX_ADDRESSES]:  # pyright: ignore[reportUnknownVariableType]
            if isinstance(item, str):
                try:
                    address = normalize(item)
                except AddressError:
                    continue
                if address not in self._addresses:
                    self._addresses.append(address)

    def add(self, text: str) -> str:
        """Save an address (normalized) and return it. Raises `AddressError`."""
        address = normalize(text)
        if address in self._addresses:
            return address
        if len(self._addresses) >= MAX_ADDRESSES:
            raise AddressError(AddressError.TOO_MANY)
        self._addresses.append(address)
        self._save()
        return address

    def remove(self, address: str) -> bool:
        if address not in self._addresses:
            return False
        self._addresses.remove(address)
        self._save()
        return True

    def _save(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".addresses-", dir=self._path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._addresses, handle, indent=2)
            os.replace(tmp, self._path)
        except OSError as exc:
            _LOGGER.warning("Couldn't save speaker addresses (%s)", type(exc).__name__)
