"""Spotify in the window: the Settings sheet's connection and the Music tab's source.

Part of `AppController`, like `library_panel`. The page renders `snapshot()` and sends
commands; `handle` checks and runs them. Which device "Play" uses is kept here: the one the
user picked, else the active one, else the first that takes commands. Playlists, devices and
searches are personal: never logged.
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

    def handle(self, kind: str, command: dict[str, Any]) -> bool:
        """Run a Spotify command. False if `kind` isn't one of them."""
        b = self._backend
        item = command.get("id")
        has_id = isinstance(item, str)
        if kind == "setSpotifyClientId" and isinstance(command.get("clientId"), str):
            self._run(b.set_spotify_client_id(command["clientId"][:MAX_CLIENT_ID_TEXT]))
        elif kind == "spotifySignIn":
            self._run(b.spotify_sign_in())
        elif kind == "spotifyCancelSignIn":
            self._run(b.spotify_cancel_sign_in())
        elif kind == "spotifySignOut":
            self.chosen_device = None
            self._run(b.spotify_sign_out(command.get("forget") is True))
        elif kind == "openSpotifyDashboard":
            self._run(b.open_spotify_dashboard())
        elif kind == "spotifyRefresh":
            self._run(b.spotify_refresh())
        elif kind == "spotifySearch" and isinstance(command.get("text"), str):
            self._run(b.spotify_search(command["text"][:MAX_SEARCH_TEXT]))
        elif kind == "spotifyPlay" and has_id:
            self._run(b.spotify_play(item, self.target))
        elif kind == "spotifyChooseDevice" and has_id:
            if any(d.id == item and not d.restricted for d in self.spotify.devices):
                self.chosen_device = item
                self._on_change()
        elif kind == "spotifyTransfer" and has_id:
            if any(d.id == item and not d.restricted for d in self.spotify.devices):
                self.chosen_device = item
                self._on_change()
                self._run(b.spotify_transfer(item))
        elif kind == "openInSpotify" and has_id:
            self._run(b.open_in_spotify(item))
        elif kind == "spotifyDismissError":
            self._run(b.spotify_dismiss_error())
        else:
            return False
        return True


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
