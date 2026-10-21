from __future__ import annotations

from pathlib import Path

import pytest

from tandem.engine.redact import Redactor


def test_known_values_get_stable_placeholders() -> None:
    redactor = Redactor()
    assert redactor.add("Living Room Speaker") == "<device-1>"
    assert redactor.add("Porch") == "<device-2>"
    assert redactor.add("living room speaker") == "<device-1>"  # same value, any case
    text = "Living Room Speaker and PORCH, then living room speaker again"
    assert redactor.redact(text) == "<device-1> and <device-2>, then <device-1> again"


def test_longest_known_value_wins() -> None:
    redactor = Redactor()
    redactor.add("Speaker")
    redactor.add("Speaker 2")
    assert redactor.redact("Speaker 2 / Speaker") == "<device-2> / <device-1>"


def test_known_values_only_match_whole_words() -> None:
    redactor = Redactor()
    redactor.add("Den")
    assert redactor.redact("Den is hidden") == "<device-1> is hidden"


def test_blank_values_are_ignored() -> None:
    redactor = Redactor()
    assert redactor.add("   ") == ""
    assert redactor.redact("") == ""
    assert redactor.redact("nothing private") == "nothing private"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("connect to 192.0.2.10:7000", "connect to <ip-1>:7000"),
        ("from 2001:db8::1 ok", "from <ip-1> ok"),
        ("link-local fe80::1%12", "<ip-1>"),
        ("mac AA:BB:CC:00:00:01", "mac <mac-1>"),
        ("id 0d7c3b2e-1f4a-4c2b-9e8d-123456789abc", "id <id-1>"),
        ("mail someone@example.com", "mail <email-1>"),
    ],
)
def test_patterns_are_redacted(text: str, expected: str) -> None:
    assert expected in Redactor().redact(text)


@pytest.mark.parametrize(
    "text",
    [
        "at 12:30:45 the stream started",
        "version 1.2.3",
        "999.300.1.1 is not an address",
        "ratio 16:9",
    ],
)
def test_lookalikes_are_left_alone(text: str) -> None:
    assert Redactor().redact(text) == text


def test_same_address_same_placeholder() -> None:
    redactor = Redactor()
    out = redactor.redact("192.0.2.10 then 192.0.2.11 then 192.0.2.10")
    assert out == "<ip-1> then <ip-2> then <ip-1>"


def test_mac_separators_share_a_placeholder() -> None:
    redactor = Redactor()
    assert redactor.redact("AA:BB:CC:00:00:01 AA-BB-CC-00-00-01") == "<mac-1> <mac-1>"


def test_user_home_is_redacted() -> None:
    # Compare whole strings only, so a failure message can't print the real folder name.
    out = Redactor().redact(f"log at {Path.home()}\\AppData")
    assert out == "log at <user-home>\\AppData", "user folder was not redacted"


def test_placeholder_does_not_register_a_known_value() -> None:
    redactor = Redactor()
    assert redactor.placeholder("192.0.2.10", "ip") == "<ip-1>"
    assert redactor.redact("Porch") == "Porch"
