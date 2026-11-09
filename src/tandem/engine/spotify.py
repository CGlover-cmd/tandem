"""Spotify as a remote, through its Web API only (Phase 6, ADR-0013, ADR-0020).

Tandem never plays Spotify audio. It signs in with the user's own Client ID (Authorization
Code with PKCE, no client secret), then lists their playlists and Spotify Connect devices,
searches the catalog, and asks Spotify to play on a device or move playback to one. The
Spotify app plays; if it plays on this PC, Tandem's router carries the sound to the speakers.

Sign-in opens Spotify's page in the system browser. Spotify sends the browser back to a
one-shot listener on 127.0.0.1 with a port picked at sign-in time: the user registers
`http://127.0.0.1/callback` (no port) and Spotify accepts any port on a loopback literal.

The Client ID and the refresh token live in a DPAPI-encrypted file (`spotify.bin`); the
access token stays in memory. Playlists, devices, searches and titles are personal: never
logged. HTTP, the browser, the listener and the secret file are passed in, so tests use fakes.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Protocol, cast
from urllib.parse import urlencode, urlsplit

from tandem.engine.events import Event, EventBus

_LOGGER = logging.getLogger(__name__)

AUTHORIZE = "https://accounts.spotify.com/authorize"
TOKEN = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
DASHBOARD = "https://developer.spotify.com/dashboard"
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://127.0.0.1{CALLBACK_PATH}"
"""What the user registers in their Spotify app: a loopback literal with no port."""
SCOPES = (
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-read-playback-state",
    "user-modify-playback-state",
)
SEARCH_LIMIT = 10  # Spotify's maximum for development-mode apps since February 2026
PLAYLIST_LIMIT = 50
MAX_QUERY = 100
MAX_ART_CACHE = 120
SIGN_IN_TIMEOUT = 300.0
TOKEN_MARGIN = 60.0
_CLIENT_ID = re.compile(r"[0-9a-f]{32}")
_ART_HOSTS = (".scdn.co", ".spotifycdn.com")
_LINK_HOSTS = ("open.spotify.com",)
_OPEN_HOSTS = ("accounts.spotify.com", "developer.spotify.com", *_LINK_HOSTS)
_ART_SIZE = 300


class SpotifyState(Enum):
    NOT_SET_UP = "not_set_up"
    """No Client ID yet."""
    SIGNED_OUT = "signed_out"
    SIGNING_IN = "signing_in"
    SIGNED_IN = "signed_in"


class SpotifyErrorCode(Enum):
    INVALID_CLIENT_ID = "invalid_client_id"
    PORT_BUSY = "port_busy"
    SIGN_IN_TIMEOUT = "sign_in_timeout"
    SIGN_IN_DENIED = "sign_in_denied"
    SIGN_IN_FAILED = "sign_in_failed"
    EXPIRED = "expired"
    """Spotify no longer accepts the saved sign-in: sign in again."""
    NO_DEVICE = "no_device"
    PREMIUM_REQUIRED = "premium_required"
    NOT_ALLOWED = "not_allowed"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    GONE = "gone"
    """The item or device isn't in the lists any more."""
    VAULT = "vault"
    """The saved sign-in can't be read (another Windows user or PC)."""


class ItemKind(Enum):
    TRACK = "track"
    ALBUM = "album"
    PLAYLIST = "playlist"


@dataclass(frozen=True, slots=True)
class SpotifyDevice:
    id: str
    name: str
    kind: str
    active: bool
    restricted: bool


@dataclass(frozen=True, slots=True)
class SpotifyItem:
    id: str
    """Tandem's key: the kind's letter and Spotify's id ("t:…", "a:…", "p:…")."""
    kind: ItemKind
    title: str
    subtitle: str
    duration: float | None
    has_art: bool
    count: int | None = None
    """How many tracks a playlist has, when Spotify says."""


@dataclass(frozen=True, slots=True)
class SpotifyStatus:
    state: SpotifyState = SpotifyState.NOT_SET_UP
    loading: bool = False
    playlists: tuple[SpotifyItem, ...] = ()
    devices: tuple[SpotifyDevice, ...] = ()
    query: str = ""
    searching: bool = False
    results: tuple[SpotifyItem, ...] = ()
    error: SpotifyErrorCode | None = None


@dataclass(frozen=True, slots=True)
class SpotifyChanged(Event):
    status: SpotifyStatus = field(default_factory=SpotifyStatus)


@dataclass(frozen=True, slots=True)
class SpotifyArt:
    data: bytes
    mimetype: str


@dataclass(frozen=True, slots=True)
class HttpReply:
    status: int
    body: Any = None
    """Parsed JSON, or None."""
    retry_after: float | None = None


class SpotifyHttp(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
    ) -> HttpReply:
        """Raises OSError (or the client's own error) when Spotify can't be reached."""
        ...

    async def image(self, url: str) -> SpotifyArt | None: ...

    async def close(self) -> None: ...


class RedirectListener(Protocol):
    @property
    def port(self) -> int: ...

    async def wait(self) -> dict[str, str]:
        """The query of the first request to the callback path."""
        ...

    async def close(self) -> None: ...


class SecretFile(Protocol):
    def read(self) -> dict[str, Any] | None: ...
    def write(self, data: dict[str, Any]) -> None: ...


Listen = Callable[[str], Awaitable[RedirectListener]]
"""Start a listener on 127.0.0.1 (any free port) for this path. Raises OSError if it can't."""
OpenUrl = Callable[[str], Awaitable[bool]]


class _ApiError(Exception):
    def __init__(self, code: SpotifyErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


def valid_client_id(text: str) -> str | None:
    """A Client ID as Spotify shows it (32 hex characters), tidied; None if it isn't one."""
    value = text.strip().lower()
    return value if _CLIENT_ID.fullmatch(value) else None


def code_challenge(verifier: str) -> str:
    """PKCE's S256 challenge for `verifier`."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def authorize_url(client_id: str, redirect_uri: str, challenge: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
            "scope": " ".join(SCOPES),
        }
    )
    return f"{AUTHORIZE}?{query}"


def safe_link(url: str, hosts: tuple[str, ...] = _LINK_HOSTS) -> str | None:
    """`url` if it is https on one of `hosts`, else None."""
    parts = urlsplit(url)
    return url if parts.scheme == "https" and parts.hostname in hosts else None


def pick_image(images: object) -> str | None:
    """The image closest to 300 px from Spotify's list, if it's on Spotify's image hosts."""
    if not isinstance(images, list):
        return None
    best: tuple[int, str] | None = None
    for image in cast(list[Any], images):
        if not isinstance(image, dict):
            continue
        url = cast(dict[str, Any], image).get("url")
        if not isinstance(url, str):
            continue
        parts = urlsplit(url)
        if parts.scheme != "https" or not (parts.hostname or "").endswith(_ART_HOSTS):
            continue
        width = cast(dict[str, Any], image).get("width")
        size = width if isinstance(width, int) else _ART_SIZE
        score = abs(size - _ART_SIZE)
        if best is None or score < best[0]:
            best = (score, url)
    return None if best is None else best[1]


class Spotify:
    def __init__(
        self,
        bus: EventBus,
        http: SpotifyHttp,
        secret_file: SecretFile,
        open_url: OpenUrl,
        listen: Listen,
        *,
        clock: Callable[[], float] = time.monotonic,
        sign_in_timeout: float = SIGN_IN_TIMEOUT,
    ) -> None:
        self._bus = bus
        self._http = http
        self._file = secret_file
        self._open_url = open_url
        self._listen = listen
        self._clock = clock
        self._timeout = sign_in_timeout
        self._status = SpotifyStatus()
        self._client_id: str | None = None
        self._refresh_token: str | None = None
        self._access: tuple[str, float] | None = None
        self._sign_in: asyncio.Future[dict[str, str]] | None = None
        self._cancelled = False
        self._search_attempt = 0
        self._uris: dict[str, str] = {}
        self._links: dict[str, str] = {}
        self._art_urls: dict[str, str] = {}
        self._art: dict[str, SpotifyArt | None] = {}
        self._refreshing: asyncio.Lock = asyncio.Lock()

    @property
    def status(self) -> SpotifyStatus:
        return self._status

    # Setup and sign-in

    async def load(self) -> None:
        """Read the saved Client ID and sign-in, then fetch the lists if signed in."""
        try:
            saved = await asyncio.to_thread(self._file.read) or {}
        except Exception as exc:  # VaultError: another user's or PC's file; leave it alone
            _LOGGER.warning("Can't read the saved Spotify sign-in (%s)", type(exc).__name__)
            self._set(state=SpotifyState.NOT_SET_UP, error=SpotifyErrorCode.VAULT)
            return
        client_id = saved.get("client_id")
        refresh = saved.get("refresh_token")
        self._client_id = valid_client_id(client_id) if isinstance(client_id, str) else None
        self._refresh_token = refresh if isinstance(refresh, str) and refresh else None
        if self._client_id is None:
            self._set(state=SpotifyState.NOT_SET_UP)
        elif self._refresh_token is None:
            self._set(state=SpotifyState.SIGNED_OUT)
        else:
            self._set(state=SpotifyState.SIGNED_IN)
            await self.refresh()

    async def set_client_id(self, text: str) -> bool:
        """Save the user's Client ID. A new one signs out (its tokens belong to the old one)."""
        client_id = valid_client_id(text)
        if client_id is None:
            self._set(error=SpotifyErrorCode.INVALID_CLIENT_ID)
            return False
        if client_id != self._client_id:
            self._client_id = client_id
            self._forget_session()
            await self._save()
        self._set(
            state=SpotifyState.SIGNED_OUT if self._refresh_token is None else self._status.state,
            error=None,
        )
        return True

    async def sign_in(self) -> None:
        """Sign in through the system browser (PKCE, loopback redirect)."""
        if self._client_id is None or self._sign_in is not None:
            return
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(16)
        try:
            listener = await self._listen(CALLBACK_PATH)
        except OSError as exc:
            _LOGGER.warning("Can't listen for Spotify's sign-in (%s)", type(exc).__name__)
            self._set(error=SpotifyErrorCode.PORT_BUSY)
            return
        redirect = f"http://127.0.0.1:{listener.port}{CALLBACK_PATH}"
        self._cancelled = False
        waiting = asyncio.ensure_future(listener.wait())
        self._sign_in = waiting
        previous = self._status.state
        self._set(state=SpotifyState.SIGNING_IN, error=None)
        try:
            url = authorize_url(self._client_id, redirect, code_challenge(verifier), state)
            if not await self._open_url(url):
                raise OSError("the browser didn't open")
            reply = await asyncio.wait_for(waiting, self._timeout)
        except TimeoutError:
            self._set(state=previous, error=SpotifyErrorCode.SIGN_IN_TIMEOUT)
            return
        except asyncio.CancelledError:
            if not self._cancelled:
                raise
            self._set(state=previous, error=None)
            return
        except Exception as exc:
            _LOGGER.warning("Spotify sign-in didn't start (%s)", type(exc).__name__)
            self._set(state=previous, error=SpotifyErrorCode.SIGN_IN_FAILED)
            return
        finally:
            self._sign_in = None
            waiting.cancel()
            await listener.close()
        if not secrets.compare_digest(reply.get("state", ""), state):
            self._set(state=previous, error=SpotifyErrorCode.SIGN_IN_FAILED)
            return
        if "code" not in reply:
            denied = reply.get("error") == "access_denied"
            code = SpotifyErrorCode.SIGN_IN_DENIED if denied else SpotifyErrorCode.SIGN_IN_FAILED
            self._set(state=previous, error=code)
            return
        form = {
            "grant_type": "authorization_code",
            "code": reply["code"],
            "redirect_uri": redirect,
            "client_id": self._client_id,
            "code_verifier": verifier,
        }
        try:
            ok = await self._token_request(form)
        except _ApiError as exc:
            self._set(state=previous, error=exc.code)
            return
        if not ok:
            self._set(state=previous, error=SpotifyErrorCode.SIGN_IN_FAILED)
            return
        self._set(state=SpotifyState.SIGNED_IN, error=None)
        await self.refresh()

    async def cancel_sign_in(self) -> None:
        if self._sign_in is not None:
            self._cancelled = True
            self._sign_in.cancel()

    async def sign_out(self, forget_client_id: bool = False) -> None:
        """Forget the sign-in (and the Client ID, if asked). Spotify's own access for the app
        is removed on Spotify's account page; the window says so."""
        await self.cancel_sign_in()
        self._forget_session()
        if forget_client_id:
            self._client_id = None
        await self._save()
        self._set(
            state=SpotifyState.NOT_SET_UP if self._client_id is None else SpotifyState.SIGNED_OUT,
            error=None,
        )

    async def open_dashboard(self) -> bool:
        """Open Spotify's developer dashboard in the browser (the setup walkthrough's step 1)."""
        return await self._open(DASHBOARD)

    # Lists

    async def refresh(self) -> None:
        """Fetch playlists and devices again."""
        if self._status.state is not SpotifyState.SIGNED_IN:
            return
        self._set(loading=True, error=None)
        try:
            playlists = await self._api("GET", "/me/playlists", {"limit": str(PLAYLIST_LIMIT)})
            devices = await self._devices()
        except _ApiError as exc:
            self._set(loading=False, error=exc.code)
            return
        self._set(loading=False, playlists=self._playlists(playlists), devices=devices)

    async def refresh_devices(self) -> None:
        if self._status.state is not SpotifyState.SIGNED_IN:
            return
        try:
            devices = await self._devices()
        except _ApiError as exc:
            self._set(error=exc.code)
            return
        self._set(devices=devices, error=None)

    async def search(self, text: str) -> None:
        query = " ".join(text.split())[:MAX_QUERY]
        self._search_attempt += 1
        attempt = self._search_attempt
        if not query or self._status.state is not SpotifyState.SIGNED_IN:
            self._set(query="", searching=False, results=())
            return
        self._set(query=query, searching=True, error=None)
        params = {"q": query, "type": "track,album,playlist", "limit": str(SEARCH_LIMIT)}
        try:
            body = await self._api("GET", "/search", params)
        except _ApiError as exc:
            if attempt == self._search_attempt:
                self._set(searching=False, results=(), error=exc.code)
            return
        if attempt != self._search_attempt:
            return  # the user typed on
        self._set(searching=False, results=self._search_results(body))

    # Playback (Spotify plays; Tandem only asks)

    async def play(self, item_id: str, device_id: str | None = None) -> bool:
        """Play a track, album or playlist, on `device_id` or on the active device."""
        uri = self._uris.get(item_id)
        if uri is None:
            self._set(error=SpotifyErrorCode.GONE)
            return False
        body: dict[str, Any] = {"uris": [uri]} if item_id.startswith("t:") else {"context_uri": uri}
        params = {"device_id": device_id} if device_id else None
        try:
            await self._api("PUT", "/me/player/play", params, body)
        except _ApiError as exc:
            self._set(error=exc.code)
            return False
        self._set(error=None)
        await self.refresh_devices()
        return True

    async def transfer(self, device_id: str) -> bool:
        """Move playback to a device and keep playing there."""
        if not any(d.id == device_id for d in self._status.devices):
            self._set(error=SpotifyErrorCode.GONE)
            return False
        try:
            await self._api("PUT", "/me/player", None, {"device_ids": [device_id], "play": True})
        except _ApiError as exc:
            self._set(error=exc.code)
            return False
        self._set(error=None)
        await self.refresh_devices()
        return True

    async def open_item(self, item_id: str) -> bool:
        """Open an item on Spotify (the link back Spotify's terms ask for)."""
        link = self._links.get(item_id)
        return link is not None and await self._open(link)

    async def artwork(self, item_id: str) -> SpotifyArt | None:
        """An item's artwork, fetched from Spotify and kept in memory only."""
        if item_id in self._art:
            return self._art[item_id]
        url = self._art_urls.get(item_id)
        if url is None:
            return None
        try:
            art = await self._http.image(url)
        except Exception as exc:
            _LOGGER.debug("Fetching Spotify artwork failed (%s)", type(exc).__name__)
            return None
        while len(self._art) >= MAX_ART_CACHE:
            self._art.pop(next(iter(self._art)))
        self._art[item_id] = art
        return art

    async def dismiss_error(self) -> None:
        self._set(error=None)

    async def close(self) -> None:
        await self.cancel_sign_in()
        await self._http.close()

    # Internals: tokens

    async def _token_request(self, form: dict[str, str]) -> bool:
        """Exchange a code or refresh token. True if Spotify gave an access token."""
        try:
            reply = await self._http.request("POST", TOKEN, form=form)
        except Exception as exc:
            _LOGGER.info("Spotify's token service couldn't be reached (%s)", type(exc).__name__)
            raise _ApiError(SpotifyErrorCode.UNAVAILABLE) from None
        body = _dict(reply.body)
        if reply.status != 200 or not isinstance(body.get("access_token"), str):
            error = body.get("error")
            _LOGGER.info(
                "Spotify refused a token request (%s, %s)",
                reply.status,
                error if isinstance(error, str) else "-",
            )
            if form["grant_type"] == "refresh_token" and error == "invalid_grant":
                raise _ApiError(SpotifyErrorCode.EXPIRED)
            if reply.status >= 500:
                raise _ApiError(SpotifyErrorCode.UNAVAILABLE)
            return False
        expires = body.get("expires_in")
        lifetime = float(expires) if isinstance(expires, int | float) else 3600.0
        self._access = (body["access_token"], self._clock() + lifetime)
        refresh = body.get("refresh_token")
        if isinstance(refresh, str) and refresh and refresh != self._refresh_token:
            self._refresh_token = refresh
            await self._save()
        elif form["grant_type"] == "authorization_code":
            await self._save()
        return True

    async def _token(self, force: bool = False) -> str:
        async with self._refreshing:
            if not force and self._access is not None:
                token, expires = self._access
                if self._clock() < expires - TOKEN_MARGIN:
                    return token
            if self._client_id is None or self._refresh_token is None:
                raise _ApiError(SpotifyErrorCode.EXPIRED)
            form = {
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
            }
            try:
                ok = await self._token_request(form)
            except _ApiError as exc:
                if exc.code is SpotifyErrorCode.EXPIRED:
                    await self._expired()
                raise
            if not ok or self._access is None:
                await self._expired()
                raise _ApiError(SpotifyErrorCode.EXPIRED)
            return self._access[0]

    async def _expired(self) -> None:
        """Spotify no longer accepts the saved sign-in: forget it and ask for a new one."""
        self._forget_session()
        await self._save()
        self._set(state=SpotifyState.SIGNED_OUT)

    def _forget_session(self) -> None:
        self._refresh_token = None
        self._access = None
        self._uris.clear()
        self._links.clear()
        self._art_urls.clear()
        self._art.clear()
        self._status = replace(
            self._status, playlists=(), devices=(), query="", searching=False, results=()
        )

    async def _save(self) -> None:
        data: dict[str, Any] = {}
        if self._client_id is not None:
            data["client_id"] = self._client_id
        if self._refresh_token is not None:
            data["refresh_token"] = self._refresh_token
        try:
            await asyncio.to_thread(self._file.write, data)
        except OSError as exc:
            _LOGGER.warning("Can't save the Spotify sign-in (%s)", type(exc).__name__)

    # Internals: the Web API

    async def _api(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Call the Web API with a fresh token (once more after a 401). Raises _ApiError."""
        for attempt in range(2):
            token = await self._token(force=attempt > 0)
            try:
                reply = await self._http.request(
                    method, API + path, token=token, params=params, json=json
                )
            except Exception as exc:
                _LOGGER.info("Spotify couldn't be reached (%s)", type(exc).__name__)
                raise _ApiError(SpotifyErrorCode.UNAVAILABLE) from None
            if reply.status == 401 and attempt == 0:
                continue
            if 200 <= reply.status < 300:
                return reply.body
            raise _ApiError(_error_code(reply))
        raise _ApiError(SpotifyErrorCode.EXPIRED)  # pragma: no cover - the loop returns or raises

    async def _devices(self) -> tuple[SpotifyDevice, ...]:
        body = await self._api("GET", "/me/player/devices")
        rows = _list(_dict(body).get("devices"))
        devices: list[SpotifyDevice] = []
        for row in rows:
            device_id = row.get("id")
            if not isinstance(device_id, str) or not device_id:
                continue  # Spotify hides the id of devices the API can't control
            devices.append(
                SpotifyDevice(
                    device_id,
                    _text(row.get("name")) or "Spotify",
                    _text(row.get("type")).lower() or "unknown",
                    row.get("is_active") is True,
                    row.get("is_restricted") is True,
                )
            )
        return tuple(devices)

    def _playlists(self, body: Any) -> tuple[SpotifyItem, ...]:
        items: list[SpotifyItem] = []
        for row in _list(_dict(body).get("items")):
            item = self._item(ItemKind.PLAYLIST, row)
            if item is not None:
                items.append(item)
        return tuple(items)

    def _search_results(self, body: Any) -> tuple[SpotifyItem, ...]:
        found: list[SpotifyItem] = []
        data = _dict(body)
        for kind, key in (
            (ItemKind.TRACK, "tracks"),
            (ItemKind.ALBUM, "albums"),
            (ItemKind.PLAYLIST, "playlists"),
        ):
            for row in _list(_dict(data.get(key)).get("items")):
                item = self._item(kind, row)
                if item is not None:
                    found.append(item)
        return tuple(found)

    def _item(self, kind: ItemKind, row: dict[str, Any]) -> SpotifyItem | None:
        spotify_id, uri, title = row.get("id"), row.get("uri"), _text(row.get("name"))
        if not isinstance(spotify_id, str) or not isinstance(uri, str) or not title:
            return None
        if not uri.startswith(f"spotify:{kind.value}:"):
            return None
        item_id = f"{kind.value[0]}:{spotify_id}"
        duration: float | None = None
        count: int | None = None
        if kind is ItemKind.TRACK:
            album = _dict(row.get("album"))
            subtitle = " · ".join(x for x in (_artists(row), _text(album.get("name"))) if x)
            images = album.get("images")
            millis = row.get("duration_ms")
            duration = float(millis) / 1000 if isinstance(millis, int | float) else None
        elif kind is ItemKind.ALBUM:
            year = _text(row.get("release_date"))[:4]
            subtitle = " · ".join(x for x in (_artists(row), year) if x)
            images = row.get("images")
        else:
            subtitle = _text(_dict(row.get("owner")).get("display_name"))
            images = row.get("images")
            # Spotify renamed a playlist's `tracks` to `items` in February 2026.
            total = _dict(row.get("items") or row.get("tracks")).get("total")
            count = total if isinstance(total, int) else None
        art = pick_image(images)
        self._uris[item_id] = uri
        link = safe_link(_text(_dict(row.get("external_urls")).get("spotify")))
        if link is not None:
            self._links[item_id] = link
        if art is not None:
            self._art_urls[item_id] = art
        return SpotifyItem(item_id, kind, title, subtitle, duration, art is not None, count)

    async def _open(self, url: str) -> bool:
        link = safe_link(url, _OPEN_HOSTS)
        if link is None:
            return False
        try:
            return await self._open_url(link)
        except OSError as exc:
            _LOGGER.info("Opening the browser failed (%s)", type(exc).__name__)
            return False

    def _set(self, **changes: Any) -> None:
        self._status = replace(self._status, **changes)
        self._bus.publish(SpotifyChanged(self._status))


def _error_code(reply: HttpReply) -> SpotifyErrorCode:
    error = _dict(_dict(reply.body).get("error"))
    reason = error.get("reason")
    if reply.status == 429:
        return SpotifyErrorCode.RATE_LIMITED
    if reply.status == 404 and reason in (None, "NO_ACTIVE_DEVICE"):
        return SpotifyErrorCode.NO_DEVICE
    if reply.status == 404:
        return SpotifyErrorCode.GONE
    if reply.status == 403 and reason == "PREMIUM_REQUIRED":
        return SpotifyErrorCode.PREMIUM_REQUIRED
    if reply.status == 403:
        return SpotifyErrorCode.NOT_ALLOWED
    if reply.status == 401:
        return SpotifyErrorCode.EXPIRED
    _LOGGER.info("Spotify answered %s", reply.status)
    return SpotifyErrorCode.UNAVAILABLE


def _dict(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _list(value: object) -> list[dict[str, Any]]:
    """The dicts in a JSON list (Spotify's lists can hold nulls)."""
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], v) for v in cast(list[Any], value) if isinstance(v, dict)]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _artists(row: dict[str, Any]) -> str:
    return ", ".join(n for n in (_text(a.get("name")) for a in _list(row.get("artists"))) if n)
