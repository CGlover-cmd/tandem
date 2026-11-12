"""'Why can't I see my speaker?': look for the usual network reasons on this PC.

AirParrot's support pages walk people through the same checks by hand: is the firewall letting
the app in, is a VPN in the way, is the receiver on the same part of the network, does the
router pass discovery at all. Tandem can look for most of them itself and name the fix.

Everything here stays on the PC. Adapter descriptions and addresses are private: they are
compared, never logged or shown; the report holds codes and counts only.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import subprocess
import sys
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

EMPTY_SCANS = 3
"""This many scans in a row that found nothing on the network: discovery is being blocked."""


class Finding(Enum):
    """One thing the check found, worst first in a report. The window holds the words."""

    OFFLINE = "offline"  # this PC has no network address
    NO_FIREWALL_RULE = "noFirewallRule"  # the installed app's firewall rule is missing
    NO_ANSWERS = "noAnswers"  # discovery found nothing: the router may block it
    OTHER_SUBNET = "otherSubnet"  # a speaker is on another part of the network (guest Wi-Fi?)
    VPN = "vpn"  # a VPN is on and may hide the home network
    HOME_ACCESS = "homeAccess"  # a speaker refused: the Home app's speaker access setting


@dataclass(frozen=True, slots=True)
class Report:
    findings: tuple[Finding, ...]
    speakers_seen: int
    """Devices the last scan found, on the network and by address."""
    other_subnet: int = 0
    """How many known speakers are outside the PC's networks."""


class ScanHistory:
    """What the last few discovery scans found (counts only)."""

    def __init__(self, keep: int = 10) -> None:
        self._multicast: deque[int] = deque(maxlen=keep)
        self.last_total = 0

    def record(self, multicast: int, by_address: int) -> None:
        self._multicast.append(multicast)
        self.last_total = multicast + by_address

    def blocked(self) -> bool:
        """The last `EMPTY_SCANS` scans of the whole network found nothing at all."""
        recent = list(self._multicast)[-EMPTY_SCANS:]
        return len(recent) == EMPTY_SCANS and not any(recent)


@dataclass(frozen=True, slots=True)
class Adapter:
    description: str
    """Private (it can name a VPN product or a company network): compared, never logged."""
    tunnel: bool = False
    """Windows calls it a tunnel or dial-up adapter."""


@dataclass(frozen=True, slots=True)
class PcNetwork:
    adapters: tuple[Adapter, ...] = ()
    networks: tuple[ipaddress.IPv4Network, ...] = ()
    """The PC's IPv4 networks (address and prefix), private."""
    firewall_rule: bool | None = None
    """Tandem's firewall rule exists; None when this isn't the installed app (nothing to
    check) or it couldn't be read."""


_VPN_WORDS = re.compile(
    r"vpn|wireguard|wintun|openvpn|tap-windows|anyconnect|globalprotect|pangp|fortinet|"
    r"forticlient|nordlynx|juniper|pulse secure|sonicwall|zscaler|cloudflare warp|expressvpn|"
    r"protonvpn|surfshark|mullvad",
    re.IGNORECASE,
)


def is_vpn(adapter: Adapter) -> bool:
    return adapter.tunnel or bool(_VPN_WORDS.search(adapter.description))


def installed_app() -> bool:
    """Running from the installer's app folder (its own python next to the uninstaller)."""
    exe = Path(sys.executable)
    return exe.parent.name.lower() == "python" and any(exe.parent.parent.glob("unins*.exe"))


_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$a=@(Get-NetAdapter|Where-Object Status -eq 'Up'|"
    "Select-Object InterfaceDescription,InterfaceType);"
    "$i=@(Get-NetIPAddress -AddressFamily IPv4|Where-Object {$_.IPAddress -notlike '127.*' "
    "-and $_.IPAddress -notlike '169.254.*'}|Select-Object IPAddress,PrefixLength);"
    "$f=@(Get-NetFirewallRule -DisplayName 'Tandem').Count;"
    "@{adapters=$a;addresses=$i;firewall=$f}|ConvertTo-Json -Depth 3 -Compress"
)

_TUNNEL_TYPES = {23, 131}  # PPP (dial-up VPNs) and tunnel


def parse(output: str, *, check_firewall: bool) -> PcNetwork:
    """Read the PowerShell script's JSON. Bad or missing parts are left out."""
    try:
        data: Any = json.loads(output or "{}")
    except ValueError:
        return PcNetwork()
    if not isinstance(data, dict):
        return PcNetwork()
    adapters: list[Adapter] = []
    for item in _items(data.get("adapters")):  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        description = item.get("InterfaceDescription")
        kind = item.get("InterfaceType")
        if isinstance(description, str):
            adapters.append(Adapter(description, isinstance(kind, int) and kind in _TUNNEL_TYPES))
    networks: list[ipaddress.IPv4Network] = []
    for item in _items(data.get("addresses")):  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        address, prefix = item.get("IPAddress"), item.get("PrefixLength")
        if not isinstance(address, str) or not isinstance(prefix, int):
            continue
        try:
            networks.append(ipaddress.IPv4Network(f"{address}/{prefix}", strict=False))
        except ValueError:
            continue
    rule = data.get("firewall")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    firewall = None
    if check_firewall and isinstance(rule, int) and not isinstance(rule, bool):
        firewall = rule > 0
    return PcNetwork(tuple(adapters), tuple(networks), firewall)


def _items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, dict)]  # pyright: ignore[reportUnknownVariableType]


class Probe:
    """Reads the PC's adapters, networks and Tandem's firewall rule (Windows, no admin)."""

    async def read(self) -> PcNetwork:  # pragma: no cover - needs Windows networking
        if sys.platform != "win32":
            return PcNetwork()
        return await asyncio.to_thread(self._read)

    def _read(self) -> PcNetwork:  # pragma: no cover - needs Windows networking
        try:
            done = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            _LOGGER.info("The network check couldn't run (%s)", type(exc).__name__)
            return PcNetwork()
        return parse(done.stdout, check_firewall=installed_app())


@dataclass
class _Checks:
    findings: list[Finding] = field(default_factory=list[Finding])

    def add(self, finding: Finding, when: bool) -> None:
        if when and finding not in self.findings:
            self.findings.append(finding)


def outside(networks: Sequence[ipaddress.IPv4Network], addresses: Sequence[str]) -> int:
    """How many of `addresses` sit in none of the PC's networks (0 if the networks are
    unknown)."""
    if not networks:
        return 0
    count = 0
    for text in set(addresses):
        try:
            address = ipaddress.IPv4Address(text)
        except ValueError:
            continue  # IPv6 or unknown: can't tell
        if not any(address in network for network in networks):
            count += 1
    return count


async def run(
    probe: Probe, scans: ScanHistory, *, speakers: Sequence[str] = (), refused: int = 0
) -> Report:
    """Run every check. `speakers` are the known speakers' addresses (private); `refused` is
    how many speakers turned Tandem away."""
    pc = await probe.read()
    checks = _Checks()
    away = outside(pc.networks, speakers)
    checks.add(Finding.OFFLINE, not pc.networks and bool(pc.adapters))
    checks.add(Finding.NO_FIREWALL_RULE, pc.firewall_rule is False)
    checks.add(Finding.NO_ANSWERS, scans.blocked())
    checks.add(Finding.OTHER_SUBNET, away > 0)
    checks.add(Finding.VPN, any(is_vpn(a) for a in pc.adapters))
    checks.add(Finding.HOME_ACCESS, refused > 0)
    order = list(Finding)
    findings = tuple(sorted(checks.findings, key=order.index))
    _LOGGER.info("Network check: %s", ", ".join(f.value for f in findings) or "nothing found")
    return Report(findings, scans.last_total, away)
