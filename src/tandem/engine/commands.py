"""Typed commands (Phase 9a): turn a line like "volume 30 on loft" into an intent.

Pure Python: no network and no machine learning, just a fixed set of verbs and a forgiving
device-name matcher (case-insensitive, partial words, small typos). `parse` returns an intent
for `tandem.engine.command_dispatch` to run, or a `Problem` that says what was missing, with
suggestions the user can pick instead.

The verbs:
- ``play`` / ``pause`` / ``next`` / ``previous`` (``stop`` pauses), optionally ``on <device>``
- ``volume <0-100> [on <device>]``, ``set the <device> volume to <n>``, ``volume up``/``down``
- ``send audio to <device>, <device> and <device>``, ``play audio on ...``, ``stop streaming``
- ``open <app> [on the TV]``
- ``turn on <switch or device>``, ``turn <switch or device> off``
- ``help``

Command text and device names are private (docs/PRIVACY.md): never log them.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Generic, Protocol, TypeVar

from tandem.engine.models import DeviceKind

MAX_COMMAND_LENGTH = 200
"""Longer input is not a command; it is refused before parsing."""


# --- What the parser works on ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Target:
    """A device a command can name."""

    id: str
    name: str
    kind: DeviceKind


@dataclass(frozen=True, slots=True)
class SwitchTarget:
    """A switch Tandem offers to the Home app (Phase 9b) that a command can turn on or off."""

    id: str
    name: str


# --- Intents -----------------------------------------------------------------------------


class MediaAction(Enum):
    PLAY = "play"
    PAUSE = "pause"
    NEXT = "next"
    PREVIOUS = "previous"


@dataclass(frozen=True, slots=True)
class Media:
    action: MediaAction
    device: Target | None = None
    """None: the dispatcher picks the device (the only connected one, or the one playing)."""


@dataclass(frozen=True, slots=True)
class SetVolume:
    level: int
    device: Target | None = None


@dataclass(frozen=True, slots=True)
class StepVolume:
    up: bool
    device: Target | None = None


@dataclass(frozen=True, slots=True)
class SendAudio:
    """Stream the PC's audio to these devices, or to every speaker when `everywhere`.
    With neither, the devices used last time."""

    devices: tuple[Target, ...] = ()
    everywhere: bool = False


@dataclass(frozen=True, slots=True)
class StopStreaming:
    pass


@dataclass(frozen=True, slots=True)
class OpenApp:
    app: str
    """The app name as typed; the dispatcher matches it against the device's app list."""
    device: Target | None = None


@dataclass(frozen=True, slots=True)
class Turn:
    """Turn a Home switch, or a device's power, on or off."""

    on: bool
    target: Target | SwitchTarget


@dataclass(frozen=True, slots=True)
class Help:
    pass


Intent = Media | SetVolume | StepVolume | SendAudio | StopStreaming | OpenApp | Turn | Help


class ProblemCode(Enum):
    EMPTY = "empty"
    TOO_LONG = "tooLong"
    NOT_UNDERSTOOD = "notUnderstood"
    UNKNOWN_DEVICE = "unknownDevice"
    AMBIGUOUS_DEVICE = "ambiguousDevice"
    UNKNOWN_TARGET = "unknownTarget"
    """``turn on X`` where X is neither a switch nor a device."""
    BAD_VOLUME = "badVolume"


@dataclass(frozen=True, slots=True)
class Problem:
    """The command couldn't be turned into an intent. Safe to show; never log it."""

    code: ProblemCode
    subject: str = ""
    """The words that didn't match, as typed (lower-cased)."""
    suggestions: tuple[str, ...] = ()
    """Whole commands the user may have meant, ready to run."""


Parsed = Intent | Problem


# --- Matching names ----------------------------------------------------------------------

_WORD = re.compile(r"[^\W_]+")
_FILLER = frozenset({"the", "my", "a", "an", "our", "this"})
_KIND_ALIASES = {
    DeviceKind.APPLE_TV: frozenset({"tv", "apple tv", "appletv", "television"}),
    DeviceKind.HOMEPOD: frozenset({"homepod", "homepod mini", "home pod"}),
}
_TYPO_CUTOFF = 0.8


def words(text: str) -> list[str]:
    """Lower-case words, punctuation dropped."""
    return _WORD.findall(text.casefold())


def _phrase_words(phrase: str) -> list[str]:
    return [w for w in words(phrase) if w not in _FILLER]


def _score(query: list[str], name: str, kind: DeviceKind | None) -> int:
    """How well the query words name this target; 0 for not at all.

    Best first: the whole name (4); every query word starts a different word of the name (3);
    a kind word such as "tv" (2); every query word is a near-miss spelling of a word of the
    name (1). Two targets that match the same way are a tie, so the user is asked which.
    """
    name_words = words(name)
    if not name_words or not query:
        return 0
    if query == name_words or "".join(query) == "".join(name_words):
        return 4
    if _cover(query, name_words, lambda q, n: n.startswith(q)):
        return 3
    if kind is not None and " ".join(query) in _KIND_ALIASES.get(kind, ()):
        return 2
    if _cover(query, name_words, _near):
        return 1
    return 0


def _near(query_word: str, name_word: str) -> bool:
    if len(query_word) < 4:
        return False
    return difflib.SequenceMatcher(None, query_word, name_word).ratio() >= _TYPO_CUTOFF


def _cover(query: list[str], name_words: list[str], matches: Callable[[str, str], bool]) -> bool:
    """Whether every query word matches a different word of the name."""
    free = list(range(len(name_words)))
    for word in query:
        hit = next((i for i in free if matches(word, name_words[i])), None)
        if hit is None:
            return False
        free.remove(hit)
    return True


class Named(Protocol):
    @property
    def name(self) -> str: ...


T = TypeVar("T", bound=Named)


@dataclass(frozen=True, slots=True)
class Match(Generic[T]):
    found: T | None = None
    candidates: tuple[T, ...] = ()
    """Equally good matches when the name is ambiguous, or close names when nothing matched."""
    score: int = 0


def match_name(phrase: str, targets: Sequence[T]) -> Match[T]:
    """The target (device, switch or app) `phrase` names: ``found`` when one fits best."""
    query = _phrase_words(phrase)
    scores = [_score(query, t.name, t.kind if isinstance(t, Target) else None) for t in targets]
    best = max(scores, default=0)
    if best > 0:
        top = tuple(t for t, score in zip(targets, scores, strict=True) if score == best)
        if len(top) == 1:
            return Match(found=top[0], score=best)
        return Match(candidates=top, score=best)
    names = [t.name for t in targets]
    close = difflib.get_close_matches(" ".join(query), [n.casefold() for n in names], 3, 0.4)
    by_name = {t.name.casefold(): t for t in targets}
    return Match(candidates=tuple(by_name[n] for n in close))


# --- Parsing -----------------------------------------------------------------------------

_POLITE = re.compile(
    r"^(?:(?:hey|ok|okay)\s+tandem\s*,?\s*|tandem\s*,\s*|please\s+|(?:can|could|would)\s+you\s+)+"
)
_TRAILING = re.compile(r"(?:\s*,?\s*please)?[\s.!?]*$")

_PREP = r"(?:on|in|to|for|at|through)"
_STOP_STREAMING = re.compile(
    r"^(?:stop|end|quit|cancel)\s+(?:the\s+)?(?:streaming|stream|sending|casting|audio|sound)"
    r"(?:\s+(?:audio|sound))?(?:\s+.*)?$"
)
_SEND_AUDIO = re.compile(
    r"^(?:(?:start\s+)?(?:send|sending|stream|streaming|route|move|cast|play)(?:ing)?)\s+"
    r"(?:the\s+|my\s+|this\s+)?(?:pc'?s?\s+|computer'?s?\s+|system\s+|desktop\s+)?"
    r"(?:audio|sound|music)\s+(?:" + _PREP + r"\s+)?(?P<devices>.+)$"
)
_SEND_TO = re.compile(
    r"^(?:start\s+)?(?:send|sending|stream|streaming|cast|casting)\s+(?:it\s+)?"
    r"(?:to|on)\s+(?P<devices>.+)$"
)
_SEND_BARE = re.compile(
    r"^(?:start\s+)?(?:send|sending|stream|streaming)"
    r"(?:\s+(?:the\s+|my\s+)?(?:pc'?s?\s+|computer'?s?\s+)?(?:audio|sound|music))?$"
)
_EVERYWHERE = re.compile(r"^(?:everywhere|all(?:\s+(?:the\s+)?(?:speakers|devices|rooms))?)$")
_LIST_SPLIT = re.compile(r"\s*(?:,|&|\+|\band\b|\bplus\b)\s*")

_MEDIA_VERBS = {
    "play": MediaAction.PLAY,
    "resume": MediaAction.PLAY,
    "unpause": MediaAction.PLAY,
    "continue": MediaAction.PLAY,
    "pause": MediaAction.PAUSE,
    "stop": MediaAction.PAUSE,
    "hold": MediaAction.PAUSE,
    "next": MediaAction.NEXT,
    "skip": MediaAction.NEXT,
    "previous": MediaAction.PREVIOUS,
    "prev": MediaAction.PREVIOUS,
    "back": MediaAction.PREVIOUS,
}
_MEDIA = re.compile(
    r"^(?:go\s+)?(?P<verb>" + "|".join(_MEDIA_VERBS) + r")"
    r"(?:\s+(?:the\s+)?(?:track|song|episode|video|music|it|playback|playing|one))?"
    r"(?:\s+(?P<rest>.+))?$"
)
_LEADING_PREP = re.compile(r"^" + _PREP + r"\s+")

_VOLUME_LEVEL = re.compile(
    r"^(?:set\s+|change\s+|make\s+)?(?:the\s+)?volume"
    r"(?:\s+(?:on|of|for|in)\s+(?P<before>.+?))?"
    r"\s+(?:to\s+|at\s+)?(?P<level>-?\d+)\s*(?:%|percent)?"
    r"(?:\s+(?:on|of|for|in)\s+(?P<after>.+))?$"
)
_DEVICE_VOLUME = re.compile(
    r"^(?:set\s+|change\s+|make\s+)?(?:the\s+)?(?P<device>.+?)(?:'s)?\s+volume\s+"
    r"(?:to\s+|at\s+)?(?P<level>-?\d+)\s*(?:%|percent)?$"
)
_VOLUME_STEP = re.compile(
    r"^(?:turn\s+)?(?:the\s+)?volume\s+(?P<dir>up|down)(?:\s+" + _PREP + r"\s+(?P<device>.+))?$"
    r"|^turn\s+(?:it\s+|the\s+volume\s+)?(?P<dir2>up|down)(?:\s+the\s+volume)?"
    r"(?:\s+" + _PREP + r"\s+(?P<device2>.+))?$"
    r"|^(?P<word>louder|quieter|softer)(?:\s+" + _PREP + r"\s+(?P<device3>.+))?$"
)
_OPEN = re.compile(
    r"^(?:open|launch|start|run)\s+(?:the\s+)?(?P<app>.+?)(?:\s+app)?"
    r"(?:\s+(?:on|in)\s+(?P<device>.+))?$"
)
_TURN_FIRST = re.compile(r"^(?:turn|switch|power)\s+(?P<state>on|off)\s+(?P<target>.+)$")
_TURN_LAST = re.compile(r"^(?:turn|switch|power)\s+(?P<target>.+?)\s+(?P<state>on|off)$")
_HELP = re.compile(r"^(?:help|\?|commands|what can (?:i|you) (?:say|do))$")

_VERBS = (
    "play",
    "pause",
    "next",
    "previous",
    "volume",
    "send",
    "stream",
    "stop",
    "open",
    "launch",
    "turn",
    "help",
)


def normalize(text: str) -> str:
    """Lower-case, single-spaced, without politeness or end punctuation."""
    text = text.replace("\N{RIGHT SINGLE QUOTATION MARK}", "'").casefold()
    text = " ".join(text.split())
    text = _POLITE.sub("", text)
    return _TRAILING.sub("", text).strip()


def parse(
    text: str,
    targets: Sequence[Target],
    switches: Sequence[SwitchTarget] = (),
) -> Parsed:
    """Understand one typed command, matching device names against `targets`."""
    if len(text) > MAX_COMMAND_LENGTH:
        return Problem(ProblemCode.TOO_LONG)
    line = normalize(text)
    if not line:
        return Problem(ProblemCode.EMPTY, suggestions=examples(targets, switches))
    return _Parser(targets, switches).parse(line)


class _Parser:
    def __init__(self, targets: Sequence[Target], switches: Sequence[SwitchTarget]) -> None:
        self._targets = targets
        self._switches = switches
        self._line = ""

    def parse(self, line: str) -> Parsed:
        self._line = line
        if _HELP.match(line):
            return Help()
        if _STOP_STREAMING.match(line):
            return StopStreaming()
        if _SEND_BARE.match(line):
            return SendAudio()
        for pattern in (_SEND_AUDIO, _SEND_TO):
            found = pattern.match(line)
            if found:
                return self._send(found["devices"])
        found = _VOLUME_STEP.match(line)
        if found:
            return self._step(found)
        found = _VOLUME_LEVEL.match(line) or _DEVICE_VOLUME.match(line)
        if found:
            return self._volume(found)
        found = _TURN_FIRST.match(line) or _TURN_LAST.match(line)
        if found:
            return self._turn(found["state"] == "on", found["target"])
        found = _MEDIA.match(line)
        if found:
            return self._media(found)
        found = _OPEN.match(line)
        if found:
            return self._open(found["app"], found["device"])
        return self._not_understood(line)

    # Each verb

    def _media(self, found: re.Match[str]) -> Parsed:
        action = _MEDIA_VERBS[found["verb"]]
        rest = found["rest"]
        if not rest:
            return Media(action)
        phrase = _LEADING_PREP.sub("", rest)
        device = self._device(phrase)
        if isinstance(device, Problem):
            unknown = device.code is ProblemCode.UNKNOWN_DEVICE
            if unknown and action is MediaAction.PLAY and not _LEADING_PREP.match(rest):
                # "play netflix": probably an app, not a device.
                return Problem(
                    device.code,
                    device.subject,
                    (f"open {phrase} on the TV", *device.suggestions),
                )
            return device
        return Media(action, device)

    def _volume(self, found: re.Match[str]) -> Parsed:
        level = int(found["level"])
        if not 0 <= level <= 100:
            return Problem(ProblemCode.BAD_VOLUME, found["level"])
        groups = found.groupdict()
        phrase = groups.get("before") or groups.get("after") or groups.get("device")
        if not phrase:
            return SetVolume(level)
        device = self._device(phrase)
        return device if isinstance(device, Problem) else SetVolume(level, device)

    def _step(self, found: re.Match[str]) -> Parsed:
        word = found["word"]
        up = (found["dir"] or found["dir2"]) == "up" if word is None else word == "louder"
        phrase = found["device"] or found["device2"] or found["device3"]
        if not phrase:
            return StepVolume(up)
        device = self._device(phrase)
        return device if isinstance(device, Problem) else StepVolume(up, device)

    def _send(self, phrase: str) -> Parsed:
        if _EVERYWHERE.match(phrase):
            return SendAudio(everywhere=True)
        devices: list[Target] = []
        for part in _LIST_SPLIT.split(phrase):
            if not part.strip():
                continue
            device = self._device(part)
            if isinstance(device, Problem):
                return device
            if device not in devices:
                devices.append(device)
        if not devices:
            return self._not_understood(phrase)
        return SendAudio(tuple(devices))

    def _open(self, app: str, phrase: str | None) -> Parsed:
        app = app.strip()
        if phrase is None:
            return OpenApp(app)
        device = self._device(phrase)
        return device if isinstance(device, Problem) else OpenApp(app, device)

    def _turn(self, on: bool, phrase: str) -> Parsed:
        switch = match_name(phrase, self._switches)
        device = match_name(phrase, self._targets)
        state = "on" if on else "off"
        if switch.found is not None and switch.score >= device.score:
            return Turn(on, switch.found)
        if device.found is not None:
            return Turn(on, device.found)
        if switch.candidates and switch.score >= device.score and switch.score > 0:
            return Problem(
                ProblemCode.AMBIGUOUS_DEVICE,
                phrase,
                tuple(f"turn {state} {s.name}" for s in switch.candidates),
            )
        if device.candidates and device.score > 0:
            return Problem(
                ProblemCode.AMBIGUOUS_DEVICE,
                phrase,
                tuple(f"turn {state} {d.name}" for d in device.candidates),
            )
        close = [*switch.candidates, *device.candidates]
        return Problem(
            ProblemCode.UNKNOWN_TARGET,
            phrase,
            tuple(f"turn {state} {t.name}" for t in close),
        )

    # Helpers

    def _device(self, phrase: str) -> Target | Problem:
        match = match_name(phrase, self._targets)
        if match.found is not None:
            return match.found
        phrase = phrase.strip()
        commands = tuple(self._with_name(phrase, t.name) for t in match.candidates)
        if match.score > 0:
            return Problem(ProblemCode.AMBIGUOUS_DEVICE, phrase, commands)
        return Problem(ProblemCode.UNKNOWN_DEVICE, phrase, commands)

    def _with_name(self, phrase: str, name: str) -> str:
        """The command as typed, with `phrase` replaced by a device's full name."""
        at = self._line.rfind(phrase)
        if at < 0:
            return name
        return f"{self._line[:at]}{name}{self._line[at + len(phrase) :]}"

    def _not_understood(self, line: str) -> Problem:
        first = line.split()[0]
        close = difflib.get_close_matches(first, _VERBS, 1, 0.6)
        suggestions: tuple[str, ...] = ("volume 0",) if first in ("mute", "silence") else ()
        if close and close[0] != first:
            fixed = f"{close[0]} {line[len(first) :].strip()}".strip()
            suggestions = (fixed,)
        examples_ = examples(self._targets, self._switches)
        return Problem(
            ProblemCode.NOT_UNDERSTOOD,
            line,
            tuple(dict.fromkeys((*suggestions, *examples_))),
        )


def examples(targets: Sequence[Target], switches: Sequence[SwitchTarget] = ()) -> tuple[str, ...]:
    """A few commands that would work here, using the names of devices on the network."""
    speaker = next((t for t in targets if t.kind is not DeviceKind.APPLE_TV), None)
    tv = next((t for t in targets if t.kind is DeviceKind.APPLE_TV), None)
    found: list[str] = ["pause", "next"]
    if speaker is not None:
        found.append(f"volume 30 on {speaker.name}")
        found.append(f"send audio to {speaker.name}")
    else:
        found.append("volume 30")
    if tv is not None:
        found.append("open Music on the TV")
        found.append("turn off the TV")
    if switches:
        found.append(f"turn on {switches[0].name}")
    found.append("stop streaming")
    return tuple(found)
