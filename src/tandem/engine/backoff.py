"""Exponential backoff with jitter for reconnects and failed scans."""

from __future__ import annotations

import random
from dataclasses import dataclass

# Beyond this many doublings every delay is already at the cap; it also avoids float overflow.
_MAX_EXPONENT = 64


@dataclass(frozen=True, slots=True)
class Backoff:
    """Delay before retry number `attempt` (0-based): initial * factor**attempt, capped.

    `jitter` spreads delays by up to that fraction either way, so several devices that dropped
    together (say, after a Wi-Fi blip) don't all reconnect at the same instant.
    """

    initial: float = 0.5
    maximum: float = 30.0
    factor: float = 2.0
    jitter: float = 0.2

    def __post_init__(self) -> None:
        if self.initial < 0 or self.maximum < self.initial:
            raise ValueError("need 0 <= initial <= maximum")
        if self.factor < 1:
            raise ValueError("factor must be >= 1")
        if not 0 <= self.jitter <= 1:
            raise ValueError("jitter must be between 0 and 1")

    def delay(self, attempt: int, rng: random.Random | None = None) -> float:
        if attempt < 0:
            raise ValueError("attempt must be >= 0")
        base = min(self.maximum, self.initial * self.factor ** min(attempt, _MAX_EXPONENT))
        spread = base * self.jitter
        jittered = base + (rng or random).uniform(-spread, spread)
        return min(self.maximum, max(0.0, jittered))
