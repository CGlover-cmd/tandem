"""The typed command parser (Phase 9a). Device names are invented (docs/PRIVACY.md)."""

from __future__ import annotations

import pytest

from tandem.engine.commands import (
    MAX_COMMAND_LENGTH,
    Help,
    Media,
    MediaAction,
    OpenApp,
    Parsed,
    Problem,
    ProblemCode,
    SendAudio,
    SetVolume,
    StepVolume,
    StopStreaming,
    SwitchTarget,
    Target,
    Turn,
    examples,
    match_name,
    normalize,
    parse,
)
from tandem.engine.models import DeviceKind

TV = Target("tv", "Living Room TV", DeviceKind.APPLE_TV)
LOFT = Target("loft", "Loft Speaker", DeviceKind.HOMEPOD)
PATIO = Target("patio", "Patio Speaker", DeviceKind.HOMEPOD)
DEN = Target("den", "Den Soundbar", DeviceKind.RECEIVER)
TARGETS = (TV, LOFT, PATIO, DEN)

MUSIC_SWITCH = SwitchTarget("music", "Tandem music")
MOVIE_SWITCH = SwitchTarget("movie", "Tandem movie mode")
SWITCHES = (MUSIC_SWITCH, MOVIE_SWITCH)


# About twenty commands people type, and what each becomes.
SAMPLES: list[tuple[str, Parsed]] = [
    ("pause", Media(MediaAction.PAUSE)),
    ("Play", Media(MediaAction.PLAY)),
    ("resume on the loft", Media(MediaAction.PLAY, LOFT)),
    ("pause patio", Media(MediaAction.PAUSE, PATIO)),
    ("stop", Media(MediaAction.PAUSE)),
    ("next track on living room", Media(MediaAction.NEXT, TV)),
    ("skip", Media(MediaAction.NEXT)),
    ("previous song", Media(MediaAction.PREVIOUS)),
    ("go back on the tv", Media(MediaAction.PREVIOUS, TV)),
    ("volume 30", SetVolume(30)),
    ("volume 30 on loft", SetVolume(30, LOFT)),
    ("set the volume on patio to 45%", SetVolume(45, PATIO)),
    ("set den soundbar volume to 20", SetVolume(20, DEN)),
    ("volume up", StepVolume(up=True)),
    ("turn the volume down on the den", StepVolume(up=False, device=DEN)),
    ("louder", StepVolume(up=True)),
    ("quieter on patio", StepVolume(up=False, device=PATIO)),
    ("send audio to loft", SendAudio((LOFT,))),
    ("play audio on loft, patio and den", SendAudio((LOFT, PATIO, DEN))),
    ("stream the pc audio to patio & loft", SendAudio((PATIO, LOFT))),
    ("send audio everywhere", SendAudio(everywhere=True)),
    ("start streaming", SendAudio()),
    ("stop streaming", StopStreaming()),
    ("stop sending audio to the den", StopStreaming()),
    ("open Netflix on the TV", OpenApp("netflix", TV)),
    ("launch the music app", OpenApp("music")),
    ("turn off the TV", Turn(on=False, target=TV)),
    ("turn the den soundbar on", Turn(on=True, target=DEN)),
    ("help", Help()),
    ("Hey Tandem, pause on the patio please!", Media(MediaAction.PAUSE, PATIO)),
]


@pytest.mark.parametrize(("text", "expected"), SAMPLES)
def test_sample_commands(text: str, expected: Parsed) -> None:
    assert parse(text, TARGETS) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("turn on tandem music", Turn(on=True, target=MUSIC_SWITCH)),
        ("switch movie mode off", Turn(on=False, target=MOVIE_SWITCH)),
        ("turn off the tv", Turn(on=False, target=TV)),
    ],
)
def test_turn_finds_switches_before_devices(text: str, expected: Parsed) -> None:
    assert parse(text, TARGETS, SWITCHES) == expected


# Device names


def test_matching_ignores_case_and_takes_partial_words() -> None:
    assert parse("pause on LOF", TARGETS) == Media(MediaAction.PAUSE, LOFT)
    assert parse("pause on liv", TARGETS) == Media(MediaAction.PAUSE, TV)


def test_matching_forgives_a_small_typo() -> None:
    assert parse("pause on patoi", TARGETS) == Media(MediaAction.PAUSE, PATIO)


def test_a_whole_name_beats_a_partial_one() -> None:
    loft = Target("k", "Loft", DeviceKind.RECEIVER)
    targets = (LOFT, loft)
    assert parse("pause loft", targets) == Media(MediaAction.PAUSE, loft)
    assert parse("pause loft speaker", targets) == Media(MediaAction.PAUSE, LOFT)


def test_a_name_written_without_spaces_matches() -> None:
    assert parse("pause livingroomtv", TARGETS) == Media(MediaAction.PAUSE, TV)


def test_kind_words_find_the_only_device_of_that_kind() -> None:
    assert parse("pause the apple tv", TARGETS) == Media(MediaAction.PAUSE, TV)
    homepods = parse("pause the homepod", TARGETS)
    assert isinstance(homepods, Problem)
    assert homepods.code is ProblemCode.AMBIGUOUS_DEVICE


def test_ambiguous_names_suggest_each_full_command() -> None:
    result = parse("volume 20 on speaker", TARGETS)
    assert result == Problem(
        ProblemCode.AMBIGUOUS_DEVICE,
        "speaker",
        ("volume 20 on Loft Speaker", "volume 20 on Patio Speaker"),
    )


def test_unknown_names_suggest_close_ones() -> None:
    result = parse("pause on garden", TARGETS)
    assert isinstance(result, Problem)
    assert result.code is ProblemCode.UNKNOWN_DEVICE
    assert result.subject == "garden"
    assert all(s.startswith("pause on ") for s in result.suggestions)


def test_one_unknown_device_in_a_list_stops_the_command() -> None:
    result = parse("send audio to loft and garage", TARGETS)
    assert isinstance(result, Problem)
    assert result.subject == "garage"


def test_a_device_named_twice_is_sent_once() -> None:
    assert parse("send audio to loft and loft speaker", TARGETS) == SendAudio((LOFT,))


def test_play_with_an_unknown_name_suggests_opening_it_as_an_app() -> None:
    result = parse("play netflix", TARGETS)
    assert isinstance(result, Problem)
    assert result.suggestions[0] == "open netflix on the TV"


def test_match_name_on_any_named_item() -> None:
    match = match_name("photos", [SwitchTarget("1", "Photos"), SwitchTarget("2", "Podcasts")])
    assert match.found == SwitchTarget("1", "Photos")
    assert match_name("anything", list[Target]()).found is None


# Problems


def test_empty_text_offers_examples() -> None:
    result = parse("   ", TARGETS)
    assert isinstance(result, Problem)
    assert result.code is ProblemCode.EMPTY
    assert "volume 30 on Loft Speaker" in result.suggestions


def test_too_long_text_is_refused() -> None:
    assert parse("a" * (MAX_COMMAND_LENGTH + 1), TARGETS) == Problem(ProblemCode.TOO_LONG)


def test_volume_outside_0_to_100_is_refused() -> None:
    assert parse("volume 130", TARGETS) == Problem(ProblemCode.BAD_VOLUME, "130")


def test_a_misspelt_verb_is_corrected_first() -> None:
    result = parse("pase on patio", TARGETS)
    assert isinstance(result, Problem)
    assert result.code is ProblemCode.NOT_UNDERSTOOD
    assert result.suggestions[0] == "pause on patio"


def test_mute_points_at_volume_zero() -> None:
    result = parse("mute", TARGETS)
    assert isinstance(result, Problem)
    assert result.suggestions[0] == "volume 0"


def test_turning_on_something_unknown() -> None:
    result = parse("turn on the lamp", TARGETS)
    assert result == Problem(ProblemCode.UNKNOWN_TARGET, "the lamp")


def test_turning_on_an_ambiguous_switch_or_device() -> None:
    switch = parse("turn on tandem", TARGETS, SWITCHES)
    assert isinstance(switch, Problem)
    assert switch.code is ProblemCode.AMBIGUOUS_DEVICE
    assert switch.suggestions == ("turn on Tandem music", "turn on Tandem movie mode")
    device = parse("turn off speaker", TARGETS)
    assert isinstance(device, Problem)
    assert device.suggestions == ("turn off Loft Speaker", "turn off Patio Speaker")


def test_an_empty_device_list_is_not_understood() -> None:
    result = parse("send audio to ,", TARGETS)
    assert isinstance(result, Problem)
    assert result.code is ProblemCode.NOT_UNDERSTOOD


# Helpers


def test_normalize() -> None:
    curly = "\N{RIGHT SINGLE QUOTATION MARK}"
    assert normalize(f"  Please   PAUSE{curly}s it!!  ") == "pause's it"
    assert normalize("could you play, please?") == "play"


def test_examples_use_names_on_the_network() -> None:
    assert examples((), ()) == ("pause", "next", "volume 30", "stop streaming")
    found = examples(TARGETS, SWITCHES)
    assert "send audio to Loft Speaker" in found
    assert "turn off the TV" in found
    assert "turn on Tandem music" in found
