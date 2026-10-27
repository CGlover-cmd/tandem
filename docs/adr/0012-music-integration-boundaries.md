# ADR-0012: Music integration boundaries

- Status: Accepted (maintainer chose the "remote and router, plus Apple Music browsing" option)
- Date: 2026-10-21

## Context
Phase 6 adds a Music tab: Tandem as a remote for Spotify and Apple Music, a player for local
files and internet radio, and Apple Music browsing. Streaming services set hard limits on what
a third-party app may do with their audio, and Tandem is a public GPL-3 project, so the lines
need to be drawn before any code is written.

What we know:
- **Spotify.** The Web API (search, library, playlists, and the Player API that controls
  Spotify Connect devices such as the Spotify app) is open to any developer. Its Developer
  Terms forbid "facilitating stream ripping or other functionalities that make it easier for
  users to capture Spotify Content", and its Developer Policy bans products that replicate
  Spotify without permission. Since February 2026 a development-mode key serves at most
  5 users and its owner needs Premium. Spotify Connect receiver clones (librespot) use
  Spotify's private protocol.
- **Apple Music.** The Apple Music API (catalog, library) and MusicKit JS (sign-in, playback in
  a web page) need a developer token signed with a MusicKit key from a paid Apple Developer
  Program membership. Full tracks in a browser need a DRM key system.
- **Tandem's window** is WebView2 (ADR-0010). The feasibility review assumed WebView2 has no
  Widevine. Music spike 2 found otherwise on the reference PC: with the Evergreen runtime,
  Widevine (software level) and PlayReady both load and build licence requests in Tandem's
  window ([findings](../spikes/music-webview2-drm.md)). Whether Apple's licence servers accept
  it is still open.
- **Windows' media controls** (`Windows.Media.Control`, "GSMTC") report and control what any
  app is playing. Music spike 1 confirmed this for the Apple Music app
  ([findings](../spikes/music-media-sessions.md)).

## Decision
- **Tandem never plays Spotify streams itself.** No Web Playback SDK in the window, no
  Spotify Connect receiver (librespot or similar). The reason is Spotify's terms, not a
  technical limit: a Spotify player inside an app whose job is to send audio elsewhere is the
  kind of capture-friendly product the terms forbid.
- **The official apps play; the router carries the sound.** Streamed music reaches AirPlay
  speakers through Tandem's general-purpose system-audio router (ADR-0005, Phases 4 and 5):
  live, no recording, nothing saved, and it doesn't know or care which app is making sound.
  Music code never touches the audio path.
- **Spotify = Web API remote only.** OAuth with PKCE (no client secret), redirect to
  `http://127.0.0.1` on a loopback port. Each user creates their own Spotify developer key and
  pastes its Client ID, because a shared development key is capped at 5 users. Spotify
  content is credited per its Developer Policy (logo and a link back to the track or album).
- **Now playing for every app** comes from Windows' media controls (GSMTC), read through the
  pywinrt packages in an engine adapter.
- **Local files and internet radio** are decoded in the engine and sent straight to the
  AirPlay sender, with no loopback capture.
- **Apple Music:** the Apple Music API and MusicKit JS for browsing and sign-in. They need a
  MusicKit key owned by the maintainer; its private key stays in `local/` and is never
  committed, and the developer token is generated from it outside the repo. Playback is handed
  to the Apple Music app unless a token test shows MusicKit JS can play full tracks inside
  Tandem's window; that test needs Tandem to let WebView2 open the sign-in popup itself
  (pywebview currently sends new windows to the system browser). If full tracks do play in
  the window, the sound still goes out through the router like any other app's.
- **Tokens** (Spotify refresh tokens, the Apple Music user token, Client IDs) live in the
  existing DPAPI credential vault (ADR-0007). Logs and diagnostics never include account
  names, playlists or listening history; titles go through `Redactor`.
- **No telemetry**, as for the rest of the app.

## Consequences
- The Music tab works for any app through now playing, and adds browsing and search for
  Spotify and Apple Music without Tandem ever holding their audio.
- Spotify setup has one extra step per user (creating a developer key), which the Connections
  tab walks them through. A further Spotify cut-back would break only the Spotify part.
- Apple Music browsing depends on a paid Apple Developer membership. A developer token shipped
  inside a public app can be lifted, so how the token reaches users is decided with the
  Apple Music browsing step.
- The Spotify and Apple Music names appear only as compatibility labels, never in Tandem's own
  branding.
- If the token test shows full tracks play in the window, a follow-up ADR records it and the
  hand-off to the Apple Music app becomes optional.
