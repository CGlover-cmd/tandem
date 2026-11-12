"""Spotify on the real engine (part of `tandem.bridge`, ADR-0021).

Mixed into `EngineBackend`, like `bridge_library`. Tandem is only a remote: the Spotify app
plays. Playlists, devices and searches are personal: never logged.
"""

from __future__ import annotations

from collections.abc import Callable

from tandem.engine.events import EventBus
from tandem.engine.service import Engine
from tandem.engine.spotify import (
    Spotify,
    SpotifyChanged,
    SpotifyDevice,
    SpotifyItem,
    SpotifyStatus,
)
from tandem.ui import backend as ui


class EngineSpotify:
    """The Settings sheet's Spotify connection and the Music tab's Spotify source."""

    _engine: Engine
    _publish: Callable[[ui.BackendEvent], None]

    def _init_spotify(self, spotify: Spotify | None) -> list[Callable[[], None]]:
        self._spotify = spotify
        bus: EventBus = self._engine.bus
        return [
            bus.subscribe(
                SpotifyChanged,
                lambda e: self._publish(ui.SpotifyChanged(spotify_snapshot(e.status))),
            )
        ]

    async def _start_spotify(self) -> None:
        if self._spotify is not None:
            await self._spotify.load()

    async def _stop_spotify(self) -> None:
        if self._spotify is not None:
            await self._spotify.close()

    def spotify(self) -> ui.SpotifySnapshot:
        return spotify_snapshot(self._spotify.status if self._spotify else SpotifyStatus())

    async def set_spotify_client_id(self, text: str) -> None:
        if self._spotify is not None:
            await self._spotify.set_client_id(text)

    async def spotify_sign_in(self) -> None:
        if self._spotify is not None:
            await self._spotify.sign_in()

    async def spotify_cancel_sign_in(self) -> None:
        if self._spotify is not None:
            await self._spotify.cancel_sign_in()

    async def spotify_sign_out(self, forget_client_id: bool) -> None:
        if self._spotify is not None:
            await self._spotify.sign_out(forget_client_id)

    async def open_spotify_dashboard(self) -> None:
        if self._spotify is not None:
            await self._spotify.open_dashboard()

    async def spotify_refresh(self) -> None:
        if self._spotify is not None:
            await self._spotify.refresh()

    async def spotify_search(self, text: str) -> None:
        if self._spotify is not None:
            await self._spotify.search(text)

    async def spotify_play(self, item_id: str, device_id: str | None) -> None:
        if self._spotify is not None:
            await self._spotify.play(item_id, device_id)

    async def spotify_transfer(self, device_id: str) -> None:
        if self._spotify is not None:
            await self._spotify.transfer(device_id)

    async def open_in_spotify(self, item_id: str) -> None:
        if self._spotify is not None:
            await self._spotify.open_item(item_id)

    async def spotify_dismiss_error(self) -> None:
        if self._spotify is not None:
            await self._spotify.dismiss_error()

    async def spotify_art(self, item_id: str) -> ui.MusicArtwork | None:
        art = await self._spotify.artwork(item_id) if self._spotify else None
        return None if art is None else ui.MusicArtwork(art.data, art.mimetype)


def spotify_snapshot(status: SpotifyStatus) -> ui.SpotifySnapshot:
    return ui.SpotifySnapshot(
        state=status.state.value,
        loading=status.loading,
        playlists=tuple(_item(i) for i in status.playlists),
        devices=tuple(_device(d) for d in status.devices),
        query=status.query,
        searching=status.searching,
        results=tuple(_item(i) for i in status.results),
        error=None if status.error is None else status.error.value,
    )


def _item(item: SpotifyItem) -> ui.SpotifyItemSnapshot:
    return ui.SpotifyItemSnapshot(
        item.id, item.kind.value, item.title, item.subtitle, item.duration, item.has_art, item.count
    )


def _device(device: SpotifyDevice) -> ui.SpotifyDeviceSnapshot:
    return ui.SpotifyDeviceSnapshot(
        device.id, device.name, device.kind, device.active, device.restricted
    )
