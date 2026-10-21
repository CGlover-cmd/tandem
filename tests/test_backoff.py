from __future__ import annotations

import random

import pytest

from tandem.engine.backoff import Backoff


def test_delay_doubles_until_the_cap() -> None:
    backoff = Backoff(initial=0.5, maximum=4.0, factor=2.0, jitter=0.0)
    assert [backoff.delay(n) for n in range(6)] == [0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_jitter_stays_within_bounds_and_cap() -> None:
    backoff = Backoff(initial=1.0, maximum=8.0, jitter=0.2)
    rng = random.Random(1)
    for attempt in range(10):
        base = min(8.0, 2.0**attempt)
        for _ in range(50):
            delay = backoff.delay(attempt, rng)
            assert base * 0.8 <= delay <= min(8.0, base * 1.2)


def test_huge_attempt_does_not_overflow() -> None:
    assert Backoff(jitter=0.0).delay(10_000) == 30.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"initial": -1.0},
        {"initial": 5.0, "maximum": 1.0},
        {"factor": 0.5},
        {"jitter": 1.5},
    ],
)
def test_invalid_settings_are_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError, match=r"."):
        Backoff(**kwargs)


def test_negative_attempt_is_rejected() -> None:
    with pytest.raises(ValueError, match="attempt"):
        Backoff().delay(-1)
