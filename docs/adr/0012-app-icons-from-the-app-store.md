# ADR-0012: App icons from the App Store lookup

- Status: Accepted
- Date: 2026-10-22

## Context
The Apple TV app launcher (Phase 3) shows the TV's apps. pyatv lists them by bundle id and
name only; the Apple TV doesn't send icons. Letters on coloured tiles weren't good enough for
a finished app. Most tvOS apps share their bundle id with their iPhone app, and Apple's public
lookup service (`itunes.apple.com/lookup?bundleId=...`) returns each listing's icon. On the
reference Apple TV it found 24 of 25 third-party apps. Built-in apps mostly have no listing.

## Decision
- **Look icons up on the App Store, once.** `tandem.ui.app_icons.AppIconStore` asks the lookup
  service in batches (the Windows region's store first, then the US store), downloads each
  icon at 256 pixels from Apple's image CDN (`*.mzstatic.com`, HTTPS only), and keeps it in the
  UI's data folder under a hashed file name. Misses are retried after a week; icons are
  refreshed after a month.
- **The window loads icons from Tandem's own loopback server** (`/app-icons/<hash>.jpg`),
  never from Apple, so the page's content policy stays `img-src 'self'`.
- **Built-in apps:** Music, Photos and TV use their iPhone app's listing (aliases). Settings,
  Search, App Store, Arcade and Computers have no listing, so the front end draws its own
  simple icons for them. Apple's artwork is never committed to the repository.
- **It can be turned off.** Settings has an "App icons" switch (on by default), saved in the
  engine settings (`app_icons`). Off, no lookups are made and tiles show letters.
- **Privacy:** the lookup tells Apple which apps are on the TV (Apple already runs the TV).
  App ids and names are never logged, only counts. Demo mode makes no lookups.

## Consequences
- The launcher shows real icons for nearly every app, after a first lookup that needs the
  internet. Offline, or with the switch off, it falls back to drawn icons and letters.
- A new network dependency in the UI host (aiohttp client, already a dependency). Failures
  are logged by type only and never block the launcher.
- If Apple changes or retires the lookup service, icons fall back to letters; nothing else
  breaks.
