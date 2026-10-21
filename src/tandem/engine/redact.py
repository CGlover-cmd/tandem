"""Replace private values with stable placeholders, for logs and diagnostics (docs/PRIVACY.md).

Known values (device names and identifiers the engine has seen) are registered with `add`.
Addresses, MAC addresses, UUIDs, email addresses and user-folder paths are caught by pattern.
Each distinct value gets one placeholder, such as ``<device-1>`` or ``<ip-2>``, that stays the
same for the life of the `Redactor`, so a log still shows which lines are about the same device.
"""

from __future__ import annotations

import ipaddress
import re
import threading
from collections.abc import Callable

_MAC = re.compile(r"(?<![0-9A-Fa-f:-])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:-])")
_UUID = re.compile(
    r"(?<![0-9A-Fa-f-])[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}(?![0-9A-Fa-f-])"
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
# Candidates only; each is confirmed with the ipaddress module, so clock times like 12:30:45
# are left alone.
_IPV6 = re.compile(r"(?<![0-9A-Fa-f:])[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7}(?:%\w+)?")
_USER_HOME = re.compile(
    r"(?:[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+|(?<![\w.])/(?:Users|home)/[^/\s\"']+)",
    re.IGNORECASE,
)


def _is_ipv4(text: str) -> bool:
    try:
        ipaddress.IPv4Address(text)
    except ValueError:
        return False
    return True


def _is_ipv6(text: str) -> bool:
    try:
        ipaddress.IPv6Address(text.split("%", 1)[0])
    except ValueError:
        return False
    return True


class Redactor:
    """Thread-safe: logging handlers may format records on any thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._placeholders: dict[tuple[str, str], str] = {}  # (category, value) -> placeholder
        self._counters: dict[str, int] = {}
        self._known: dict[str, str] = {}  # lower-cased known value -> placeholder
        self._known_pattern: re.Pattern[str] | None = None

    def add(self, value: str, category: str = "device") -> str:
        """Register a private value (e.g. a device name) and return its placeholder."""
        value = value.strip()
        if not value:
            return value
        with self._lock:
            placeholder = self._placeholder_locked(category, value.lower())
            if value.lower() not in self._known:
                self._known[value.lower()] = placeholder
                self._known_pattern = None
            return placeholder

    def placeholder(self, value: str, category: str) -> str:
        """Return the placeholder for `value` without registering it as a known value."""
        with self._lock:
            return self._placeholder_locked(category, value.lower())

    def redact(self, text: str) -> str:
        if not text:
            return text
        text = self._redact_known(text)
        text = _USER_HOME.sub("<user-home>", text)
        text = _EMAIL.sub(lambda m: self.placeholder(m.group(0), "email"), text)
        text = _MAC.sub(lambda m: self.placeholder(m.group(0).replace("-", ":"), "mac"), text)
        text = _UUID.sub(lambda m: self.placeholder(m.group(0), "id"), text)
        text = _IPV4.sub(self._ip_or_original(_is_ipv4), text)
        return _IPV6.sub(self._ip_or_original(_is_ipv6), text)

    def _ip_or_original(self, valid: Callable[[str], bool]) -> Callable[[re.Match[str]], str]:
        def replace(match: re.Match[str]) -> str:
            found = match.group(0)
            return self.placeholder(found, "ip") if valid(found) else found

        return replace

    def _redact_known(self, text: str) -> str:
        with self._lock:
            if not self._known:
                return text
            if self._known_pattern is None:
                # Longest first, so "Living Room Speaker 2" wins over "Living Room Speaker".
                terms = sorted(self._known, key=len, reverse=True)
                self._known_pattern = re.compile(
                    "|".join(rf"(?<!\w){re.escape(term)}(?!\w)" for term in terms), re.IGNORECASE
                )
            pattern, known = self._known_pattern, dict(self._known)
        return pattern.sub(lambda m: known[m.group(0).lower()], text)

    def _placeholder_locked(self, category: str, value: str) -> str:
        key = (category, value)
        existing = self._placeholders.get(key)
        if existing is not None:
            return existing
        count = self._counters.get(category, 0) + 1
        self._counters[category] = count
        placeholder = f"<{category}-{count}>"
        self._placeholders[key] = placeholder
        return placeholder
