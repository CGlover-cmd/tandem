# ADR-0021: Spotify connection

- Status: Accepted
- Date: 2026-11-08

## Context
ADR-0013 makes Tandem a Spotify remote through the Web API only, with each user's own Client
ID, PKCE and tokens in the DPAPI vault. Building it needed a few more choices. Spotify's rules
as of November 2026:
- Redirect URIs must match exactly, except loopback IP literals: register
  `http://127.0.0.1/callback` with no port and any port may be used at sign-in. `localhost`
  is not allowed; plain HTTP is allowed only on loopback.
- Since February 2026 a development-mode app needs its owner to have Premium, serves at most
  5 users, and search returns at most 10 results per type. A playlist's `tracks` field became
  `items`, and `GET /playlists/{id}/tracks` is gone (`/items` works only for playlists the user
  owns or collaborates on). The Player API (devices, transfer, play) is unchanged.
- PKCE refresh may or may not return a new refresh token; `invalid_grant` means the sign-in is
  no longer accepted.

## Decision
- **Setup in Settings → Connections.** A walkthrough opens Spotify's developer dashboard in the
  system browser, shows the redirect address with a Copy button, takes the Client ID (checked
  to be 32 hex characters) and signs in. One fixed address, `http://127.0.0.1/callback`, is
  the only thing the user copies.
- **Sign-in in the system browser, not the window.** Tandem starts a one-shot listener on
  127.0.0.1 with a free port, opens Spotify's page with that port in the redirect, checks the
  `state`, exchanges the code with the PKCE verifier, and closes the listener. It gives up after
  5 minutes or when the user cancels. The window never sees the user's Spotify password.
- **Storage.** The Client ID and refresh token are in `spotify.bin`, encrypted with DPAPI for
  the Windows user (the same `EncryptedJsonFile` as the credential vault). The access token
  stays in memory. A file another user or PC wrote is left alone; setting up again replaces it.
  Signing out keeps the Client ID; "Remove Spotify" forgets both.
- **Scopes:** `playlist-read-private`, `playlist-read-collaborative`,
  `user-read-playback-state`, `user-modify-playback-state`. Nothing else.
- **What the Music tab does:** the user's playlists, Spotify Connect devices (with "Play here"
  to move playback), and search of tracks, albums and playlists (10 each). Pressing an item
  plays it on the chosen device, else the active one; playlists play as a context, so no
  playlist contents are fetched. Devices Spotify marks restricted are shown but not offered.
- **Errors are codes** (no device, Premium needed, rate limited, sign-in expired, ...); the
  words are in `web/src/strings.ts`.
- **Credit and link back.** Every item has "Open in Spotify" (its `open.spotify.com` link) and
  the source carries a text credit. Artwork is fetched from Spotify's image hosts through
  Tandem's server, kept in memory, and served with a sandboxing CSP.
- **Privacy.** Playlists, device names, searches and tokens are never logged; the window shows
  them and nothing else does.

## Consequences
- Tandem needs no shared Spotify key and works for anyone with Premium who makes their own
  app. Each user's own app is in development mode, which is enough for one person.
- The Spotify logo isn't in the repo: Spotify's brand assets come with their own terms. The
  text credit and per-item link back stand in for it; adding the official logo is a follow-up
  once its terms are checked.
- If Spotify changes the Web API again, only `engine/spotify.py` should need to follow.
