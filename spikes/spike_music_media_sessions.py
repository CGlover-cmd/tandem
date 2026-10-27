"""Music spike 1: read and control the PC's media sessions (Windows.Media.Control, "GSMTC").

Throwaway spike code (Phase 6, Music). It answers: can Tandem see what Spotify, Apple Music or
any other app is playing, follow changes without polling, and send play / pause / next to the
app that is playing? Findings go into docs/spikes/music-media-sessions.md.

It uses the pywinrt projections (`winrt-Windows.Media.Control` and the Foundation and
Storage.Streams packages it needs).

Privacy: song titles, artists, albums and artwork are never printed or saved. The script prints
only each session's app id, its playback status, timeline numbers and yes/no flags (for
example "has a title: yes"). App ids name the app (e.g. `Spotify.exe`), not the person.

Usage (from the repo root, with the dev virtualenv's python.exe):
    python spikes/spike_music_media_sessions.py list
    python spikes/spike_music_media_sessions.py watch [--seconds 30]
    python spikes/spike_music_media_sessions.py control --app Spotify --action toggle
        actions: play, pause, toggle, next, previous
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import timedelta
from typing import Any

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSession as Session,
)
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as Manager,
)
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
)

STATUS_NAMES = {
    Status.CLOSED: "closed",
    Status.OPENED: "opened",
    Status.CHANGING: "changing",
    Status.STOPPED: "stopped",
    Status.PLAYING: "playing",
    Status.PAUSED: "paused",
}


def app_id(session: Session) -> str:
    """The app's id, trimmed to its last path part in case an app reports a full path."""
    raw = session.source_app_user_model_id or "(none)"
    return raw.replace("/", "\\").rsplit("\\", 1)[-1]


def yes(flag: object) -> str:
    return "yes" if flag else "no"


def seconds(value: timedelta | None) -> str:
    return "-" if value is None else f"{value.total_seconds():.1f}s"


async def describe(session: Session) -> list[str]:
    lines = [f"app id: {app_id(session)}"]
    playback = session.get_playback_info()
    status = STATUS_NAMES.get(playback.playback_status, str(playback.playback_status))
    controls = playback.controls
    lines.append(f"  status: {status}")
    lines.append(
        "  controls enabled: "
        f"play={yes(controls.is_play_enabled)} pause={yes(controls.is_pause_enabled)} "
        f"toggle={yes(controls.is_play_pause_toggle_enabled)} "
        f"next={yes(controls.is_next_enabled)} previous={yes(controls.is_previous_enabled)} "
        f"seek={yes(controls.is_playback_position_enabled)} "
        f"shuffle={yes(controls.is_shuffle_enabled)} repeat={yes(controls.is_repeat_enabled)}"
    )
    lines.append(
        f"  shuffle on: {playback.is_shuffle_active}  repeat mode: {playback.auto_repeat_mode}"
    )

    timeline = session.get_timeline_properties()
    lines.append(
        f"  timeline: position={seconds(timeline.position)} start={seconds(timeline.start_time)} "
        f"end={seconds(timeline.end_time)} seekable range={seconds(timeline.min_seek_time)}"
        f"..{seconds(timeline.max_seek_time)}"
    )
    updated: Any = timeline.last_updated_time
    if updated is not None and updated.year > 1601:
        age = time.time() - updated.timestamp()
        lines.append(f"  timeline last updated: {age:.1f}s ago")
    else:
        lines.append("  timeline last updated: never")

    try:
        props = await session.try_get_media_properties_async()
    except OSError as error:
        lines.append(f"  media properties: failed ({type(error).__name__})")
        return lines
    lines.append(
        f"  has a title: {yes(props.title)}  artist: {yes(props.artist)}  "
        f"album: {yes(props.album_title)}  album artist: {yes(props.album_artist)}  "
        f"track number: {yes(props.track_number)}  genres: {len(list(props.genres or []))}"
    )
    try:  # the enum lives in winrt-Windows.Media, which we don't install
        lines.append(f"  playback type: {props.playback_type}")
    except AttributeError:
        lines.append("  playback type: (needs winrt-Windows.Media)")
    thumb = props.thumbnail
    if thumb is None:
        lines.append("  thumbnail: none")
    else:
        try:
            stream = await thumb.open_read_async()
            lines.append(f"  thumbnail: yes, {stream.content_type or '?'}, {stream.size} bytes")
        except OSError as error:
            lines.append(f"  thumbnail: present but unreadable ({type(error).__name__})")
    return lines


async def manager() -> Manager:
    return await Manager.request_async()


async def cmd_list() -> int:
    mgr = await manager()
    sessions = list(mgr.get_sessions())
    current = mgr.get_current_session()
    print(f"{len(sessions)} session(s); current: {app_id(current) if current else '(none)'}")
    for session in sessions:
        for line in await describe(session):
            print(line)
    return 0


async def cmd_watch(duration: float) -> int:
    """Subscribe to every change event and print a line when one fires (no polling)."""
    loop = asyncio.get_running_loop()
    mgr = await manager()
    start = time.monotonic()
    tokens: list[tuple[Any, str, Any]] = []
    counts: dict[str, int] = {}

    def note(kind: str, who: str) -> None:
        key = f"{kind} ({who})"
        counts[key] = counts.get(key, 0) + 1
        print(f"  +{time.monotonic() - start:5.1f}s  {kind:<22} {who}", flush=True)

    def hook(session: Session) -> None:
        who = app_id(session)
        for kind, add in (
            ("media properties", session.add_media_properties_changed),
            ("playback info", session.add_playback_info_changed),
            ("timeline", session.add_timeline_properties_changed),
        ):
            token = add(lambda _s, _a, k=kind, w=who: loop.call_soon_threadsafe(note, k, w))
            tokens.append((session, kind, token))

    def on_sessions_changed(_sender: Any, _args: Any) -> None:
        names = sorted(app_id(s) for s in mgr.get_sessions())
        loop.call_soon_threadsafe(note, "sessions changed", ", ".join(names) or "(none)")

    def on_current_changed(_sender: Any, _args: Any) -> None:
        current = mgr.get_current_session()
        loop.call_soon_threadsafe(
            note, "current session", app_id(current) if current else "(none)"
        )

    for session in mgr.get_sessions():
        hook(session)
    t1 = mgr.add_sessions_changed(on_sessions_changed)
    t2 = mgr.add_current_session_changed(on_current_changed)
    print(f"Watching for {duration:.0f}s. Play, pause or skip in any app now.", flush=True)
    await asyncio.sleep(duration)
    mgr.remove_sessions_changed(t1)
    mgr.remove_current_session_changed(t2)
    for session, kind, token in tokens:
        remove = {
            "media properties": session.remove_media_properties_changed,
            "playback info": session.remove_playback_info_changed,
            "timeline": session.remove_timeline_properties_changed,
        }[kind]
        remove(token)
    print("Event counts:")
    for key, value in sorted(counts.items()):
        print(f"  {key}: {value}")
    if not counts:
        print("  none")
    return 0


async def cmd_control(app: str, action: str) -> int:
    mgr = await manager()
    matches = [s for s in mgr.get_sessions() if app.lower() in app_id(s).lower()]
    if not matches:
        print(f"No session whose app id contains {app!r}.")
        return 1
    session = matches[0]
    calls = {
        "play": session.try_play_async,
        "pause": session.try_pause_async,
        "toggle": session.try_toggle_play_pause_async,
        "next": session.try_skip_next_async,
        "previous": session.try_skip_previous_async,
    }
    before = STATUS_NAMES.get(session.get_playback_info().playback_status, "?")
    accepted = await calls[action]()
    await asyncio.sleep(1.5)
    after = STATUS_NAMES.get(session.get_playback_info().playback_status, "?")
    print(f"{app_id(session)}: {action} accepted={yes(accepted)}  status {before} -> {after}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    watch = sub.add_parser("watch")
    watch.add_argument("--seconds", type=float, default=30)
    control = sub.add_parser("control")
    control.add_argument("--app", required=True, help="part of the app id, e.g. Spotify")
    control.add_argument(
        "--action", required=True, choices=["play", "pause", "toggle", "next", "previous"]
    )
    args = parser.parse_args()
    if args.command == "list":
        return asyncio.run(cmd_list())
    if args.command == "watch":
        return asyncio.run(cmd_watch(args.seconds))
    return asyncio.run(cmd_control(args.app, args.action))


if __name__ == "__main__":
    sys.exit(main())
