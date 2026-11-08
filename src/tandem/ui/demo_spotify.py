"""Spotify for `DemoBackend`: invented playlists, devices and results only (docs/PRIVACY.md).

Nothing reaches Spotify and no browser opens. Any 32-character hex Client ID is accepted;
signing in just waits a moment, then shows the invented lists.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace

from tandem.ui.backend import (
    BackendEvent,
    MusicArtwork,
    SpotifyChanged,
    SpotifyDeviceSnapshot,
    SpotifyItemSnapshot,
    SpotifySnapshot,
)

DEMO_PLAYLISTS = (
    SpotifyItemSnapshot("p:demo1", "playlist", "Sunday Morning", "Demo User", None, True, 24),
    SpotifyItemSnapshot("p:demo2", "playlist", "Focus Beats", "Demo User", None, True, 57),
    SpotifyItemSnapshot("p:demo3", "playlist", "Road Trip Mix", "Example Friend", None, True, 31),
)
DEMO_DEVICES = (
    SpotifyDeviceSnapshot("demo-dev-1", "Demo Laptop", "computer", True),
    SpotifyDeviceSnapshot("demo-dev-2", "Example Phone", "smartphone"),
    SpotifyDeviceSnapshot("demo-dev-3", "Sample Smart TV", "tv", restricted=True),
)
DEMO_RESULTS = (
    SpotifyItemSnapshot("t:demo1", "track", "Paper Lanterns", "Example Duo · Lights", 214.0, True),
    SpotifyItemSnapshot("t:demo2", "track", "Lantern Song", "Sample Singer · Glow", 187.0, True),
    SpotifyItemSnapshot("a:demo1", "album", "Lights", "Example Duo · 2022", None, True),
    SpotifyItemSnapshot("p:demo4", "playlist", "Lantern Evenings", "Demo Curator", None, True),
)
_COLOURS = {"p": ("#1DB954", "#1E3264"), "t": ("#E8115B", "#7358FF"), "a": ("#F59B23", "#E91429")}


def _art(colours: tuple[str, str]) -> bytes:
    start, end = colours
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{start}"/><stop offset="1" stop-color="{end}"/>'
        '</linearGradient></defs><rect width="120" height="120" fill="url(#g)"/></svg>'
    ).encode()


class DemoSpotify:
    """Mixed into `DemoBackend`."""

    _publish: Callable[[BackendEvent], None]
    _sleep: Callable[[float], Awaitable[None]]
    _delay: float

    def _init_spotify(self) -> None:
        self._spotify = SpotifySnapshot()
        self._spotify_client: str | None = None
        self.spotify_played: list[tuple[str, str | None]] = []
        self.spotify_opened: list[str] = []

    def spotify(self) -> SpotifySnapshot:
        return self._spotify

    async def set_spotify_client_id(self, text: str) -> None:
        value = text.strip().lower()
        if len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
            self._set_spotify(error="invalid_client_id")
            return
        self._spotify_client = value
        state = "signed_out" if self._spotify.state == "not_set_up" else self._spotify.state
        self._set_spotify(state=state, error=None)

    async def spotify_sign_in(self) -> None:
        if self._spotify_client is None or self._spotify.state == "signing_in":
            return
        self._set_spotify(state="signing_in", error=None)
        await self._sleep(self._delay)
        if self._spotify.state != "signing_in":
            return  # cancelled meanwhile
        self._set_spotify(state="signed_in", playlists=DEMO_PLAYLISTS, devices=DEMO_DEVICES)

    async def spotify_cancel_sign_in(self) -> None:
        if self._spotify.state == "signing_in":
            self._set_spotify(state="signed_out")

    async def spotify_sign_out(self, forget_client_id: bool) -> None:
        if forget_client_id:
            self._spotify_client = None
        self._spotify = SpotifySnapshot(
            state="signed_out" if self._spotify_client else "not_set_up"
        )
        self._publish(SpotifyChanged(self._spotify))

    async def open_spotify_dashboard(self) -> None:
        self.spotify_opened.append("dashboard")

    async def spotify_refresh(self) -> None:
        if self._spotify.state == "signed_in":
            devices = self._spotify.devices or DEMO_DEVICES
            self._set_spotify(playlists=DEMO_PLAYLISTS, devices=devices)

    async def spotify_search(self, text: str) -> None:
        query = " ".join(text.split())
        words = query.casefold().split()
        results = tuple(
            r
            for r in DEMO_RESULTS
            if words and all(w in f"{r.title} {r.subtitle}".casefold() for w in words)
        )
        self._set_spotify(query=query, searching=False, results=results)

    async def spotify_play(self, item_id: str, device_id: str | None) -> None:
        known = {i.id for i in (*self._spotify.playlists, *self._spotify.results)}
        if item_id not in known:
            self._set_spotify(error="gone")
            return
        if device_id is None:
            self._set_spotify(error="no_device")
            return
        self.spotify_played.append((item_id, device_id))
        self._activate(device_id)

    async def spotify_transfer(self, device_id: str) -> None:
        self._activate(device_id)

    async def open_in_spotify(self, item_id: str) -> None:
        self.spotify_opened.append(item_id)

    async def spotify_dismiss_error(self) -> None:
        self._set_spotify(error=None)

    async def spotify_art(self, item_id: str) -> MusicArtwork | None:
        colours = _COLOURS.get(item_id[:1])
        return None if colours is None else MusicArtwork(_art(colours), "image/svg+xml")

    def _activate(self, device_id: str) -> None:
        devices = tuple(replace(d, active=d.id == device_id) for d in self._spotify.devices)
        self._set_spotify(devices=devices, error=None)

    def _set_spotify(self, **changes: object) -> None:
        self._spotify = replace(self._spotify, **changes)  # pyright: ignore[reportArgumentType]
        self._publish(SpotifyChanged(self._spotify))
