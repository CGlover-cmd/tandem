"""Cast screen, in plain Python (part of `AppController`, ADR-0010; ADR-0006 addendum).

The window's Cast sheet picks a screen, a quality and whether the PC's sound goes too; the
tray offers Stop. One cast at a time, to one Apple TV.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from tandem.ui.backend import Backend, CastQuality, CastSnapshot, CastState, ScreenInfo
from tandem.ui.window_commands import CommandTable, Fields

Runner = Callable[[Coroutine[Any, Any, None]], object]

ACTIVE = frozenset({CastState.STARTING, CastState.PLAYING})


class CastPanel:
    def __init__(self, backend: Backend, run: Runner, *, on_change: Callable[[], None]) -> None:
        self._backend = backend
        self._run = run
        self._on_change = on_change
        self.screens: list[ScreenInfo] = []
        self.cast: CastSnapshot | None = None
        self._loading = False

    @property
    def casting_to(self) -> str | None:
        """The TV the screen is cast to, while it starts or plays."""
        cast = self.cast
        return cast.device_id if cast is not None and cast.state in ACTIVE else None

    def snapshot(self) -> dict[str, Any]:
        cast = self.cast
        return {
            "screens": [
                {"index": s.index, "width": s.width, "height": s.height, "primary": s.primary}
                for s in self.screens
            ],
            "active": None
            if cast is None
            else {
                "deviceId": cast.device_id,
                "state": cast.state.value,
                "problem": None if cast.problem is None else {"code": cast.problem},
            },
        }

    def load_screens(self) -> None:
        """Look at the PC's displays again (the Cast sheet opens; a monitor may have changed)."""
        if not self._loading:
            self._loading = True
            self._run(self._load_screens())

    def stop(self) -> None:
        self._run(self._backend.stop_cast())

    def register(self, table: CommandTable) -> None:
        backend, run = self._backend, self._run

        def cast_screen(f: Fields) -> None:
            device_id, screen = f.text("id"), f.integer("screen")
            quality = f.choice(CastQuality, "quality", CastQuality.STANDARD.value)
            sound = f.flag("sound") if f.has("sound") else True
            if device_id is None or screen is None or quality is None or sound is None:
                return
            run(backend.cast_screen(device_id, screen, quality, sound))

        table.on("castScreen", cast_screen)
        table.on("stopCast", lambda _f: self.stop())
        table.on("loadScreens", lambda _f: self.load_screens())

    async def _load_screens(self) -> None:
        try:
            screens = await self._backend.screens()
        finally:
            self._loading = False
        if screens != self.screens:
            self.screens = screens
            self._on_change()
