"""Spotify in the window: the Settings sheet's connection and the Music tab's source.

Part of `AppController`, like `library_panel`. The page renders `snapshot()` and sends commands;
`register` adds them to the window's command table. Which device "Play" uses is kept here: the
one the user picked, else the active one, else the first that takes commands. Playlists, devices
and searches are personal: never logged.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from tandem.ui.backend import (
    Backend,
    SpotifyDeviceSnapshot,
    SpotifyItemSnapshot,
    SpotifySnapshot,
)
from tandem.ui.window_commands import CommandTable, Fields, Handler

MAX_SEARCH_TEXT = 100
MAX_CLIENT_ID_TEXT = 200

Runner = Callable[[Coroutine[Any, Any, None]], object]


class SpotifyPanel:
    def __init__(self, backend: Backend, run: Runner, *, on_change: Callable[[], None]) -> None:
        self._backend = backend
        self._run = run
        self._on_change = on_change
        self.spotify: SpotifySnapshot = SpotifySnapshot()
        self.chosen_device: str | None = None

    def load(self) -> None:
        self.spotify = self._backend.spotify()

    def changed(self, spotify: SpotifySnapshot) -> None:
        self.spotify = spotify
        if self.chosen_device is not None and not any(
            d.id == self.chosen_device for d in spotify.devices
        ):
            self.chosen_device = None

    @property
    def target(self) -> str | None:
        """The device "Play" uses."""
        devices = [d for d in self.spotify.devices if not d.restricted]
        if self.chosen_device is not None and any(d.id == self.chosen_device for d in devices):
            return self.chosen_device
        active = next((d for d in devices if d.active), None)
        if active is not None:
            return active.id
        return devices[0].id if devices else None

    def snapshot(self) -> dict[str, Any]:
        s = self.spotify
        return {
            "spotify": {
                "state": s.state,
                "loading": s.loading,
                "redirectUri": s.redirect_uri,
                "error": s.error,
                "playlists": [_item(i) for i in s.playlists],
                "devices": [_device(d) for d in s.devices],
                "target": self.target,
                "query": s.query,
                "searching": s.searching,
                "results": [_item(i) for i in s.results],
            }
        }

    async def close(self) -> None:
        """At shutdown: stop waiting for a sign-in, so quitting doesn't wait for the browser."""
        await self._backend.spotify_cancel_sign_in()

    def register(self, table: CommandTable) -> None:
        """The Spotify commands."""
        b, run = self._backend, self._run

        def plain(action: Callable[[], Coroutine[Any, Any, None]]) -> Handler:
            def handler(_f: Fields) -> None:
                run(action())

            return handler

        def set_client_id(f: Fields) -> None:
            client_id = f.text("clientId")
            if client_id is not None:
                run(b.set_spotify_client_id(client_id[:MAX_CLIENT_ID_TEXT]))

        def sign_out(f: Fields) -> None:
            self.chosen_device = None
            run(b.spotify_sign_out(f.flag("forget") is True))

        def search(f: Fields) -> None:
            text = f.text("text")
            if text is not None:
                run(b.spotify_search(text[:MAX_SEARCH_TEXT]))

        def choose(device_id: str) -> bool:
            if any(d.id == device_id and not d.restricted for d in self.spotify.devices):
                self.chosen_device = device_id
                self._on_change()
                return True
            return False

        def transfer(device_id: str) -> None:
            if choose(device_id):
                run(b.spotify_transfer(device_id))

        table.on("setSpotifyClientId", set_client_id)
        table.on("spotifySignIn", plain(b.spotify_sign_in))
        table.on("spotifyCancelSignIn", plain(b.spotify_cancel_sign_in))
        table.on("spotifySignOut", sign_out)
        table.on("openSpotifyDashboard", plain(b.open_spotify_dashboard))
        table.on("spotifyRefresh", plain(b.spotify_refresh))
        table.on("spotifySearch", search)
        table.on_id("spotifyPlay", lambda item_id: run(b.spotify_play(item_id, self.target)))
        table.on_id("spotifyChooseDevice", choose)
        table.on_id("spotifyTransfer", transfer)
        table.on_id("openInSpotify", lambda item_id: run(b.open_in_spotify(item_id)))
        table.on("spotifyDismissError", plain(b.spotify_dismiss_error))


def _item(item: SpotifyItemSnapshot) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "title": item.title,
        "subtitle": item.subtitle,
        "duration": item.duration,
        "hasArt": item.has_art,
        "count": item.count,
    }


def _device(device: SpotifyDeviceSnapshot) -> dict[str, Any]:
    return {
        "id": device.id,
        "name": device.name,
        "kind": device.kind,
        "active": device.active,
        "restricted": device.restricted,
    }
