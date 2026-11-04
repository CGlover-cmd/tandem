"""Windows' media controls (GSMTC) through the pywinrt projections (Music spike 1)."""

from __future__ import annotations

import importlib.util
from typing import Any

from tandem.engine.pc_media import MediaSessions, NoMediaSessions, PcMediaCommand, PcNowPlaying
from tandem.engine.pc_media import friendly_app as _friendly

_STATUS = {4: "playing", 5: "paused", 3: "stopped"}


class WindowsMediaSessions:  # pragma: no cover - needs Windows' media service; checked by hand
    def __init__(self) -> None:
        self._manager: Any = None

    async def _session(self) -> Any:
        from winrt.windows.media.control import (  # pyright: ignore[reportMissingModuleSource]
            GlobalSystemMediaTransportControlsSessionManager as Manager,
        )

        if self._manager is None:
            self._manager = await Manager.request_async()
        return self._manager.get_current_session()

    async def current(self) -> PcNowPlaying | None:
        session: Any = await self._session()
        if session is None:
            return None
        props: Any = await session.try_get_media_properties_async()
        info: Any = session.get_playback_info()
        controls: Any = info.controls
        return PcNowPlaying(
            state=_STATUS.get(int(info.playback_status), "other"),
            title=props.title or None,
            artist=props.artist or None,
            album=props.album_title or None,
            app=_friendly(session.source_app_user_model_id),
            can_play_pause=bool(
                controls.is_play_pause_toggle_enabled
                or controls.is_play_enabled
                or controls.is_pause_enabled
            ),
            can_next=bool(controls.is_next_enabled),
            can_previous=bool(controls.is_previous_enabled),
        )

    async def command(self, command: PcMediaCommand) -> bool:
        session: Any = await self._session()
        if session is None:
            return False
        if command is PcMediaCommand.NEXT:
            return bool(await session.try_skip_next_async())
        if command is PcMediaCommand.PREVIOUS:
            return bool(await session.try_skip_previous_async())
        return bool(await session.try_toggle_play_pause_async())


def media_sessions() -> MediaSessions:  # pragma: no cover - depends on the PC
    try:
        found = importlib.util.find_spec("winrt.windows.media.control") is not None
    except (ImportError, ValueError):
        found = False
    return WindowsMediaSessions() if found else NoMediaSessions()
