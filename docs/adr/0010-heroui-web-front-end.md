# ADR-0010: HeroUI web front end in a WebView2 window

- Status: Accepted (maintainer, 2026-10-21)
- Date: 2026-10-21
- Supersedes: ADR-0002; replaces the QML parts of ADR-0008

## Context
The maintainer wants the interface built with [HeroUI](https://heroui.com) (React components,
MIT) for an Apple-like look, and the project goal describes Tandem as a web app. Users should
also be able to pick the window background (neutral tones or colour gradients) in Settings.
ADR-0002 chose PySide6 + QML, and the Phase 2 shell (device grid, PIN pairing sheet, tray menu)
is built that way against the UI's `Backend` contract (ADR-0008).

The front end has to sit beside a Python engine (pyatv, ADR-0001), keep a tray menu, stay
GPL-3 compatible (ADR-0003), need no extra devices, run on Windows 10 22H2+ and 11, and meet
the targets in the roadmap (cold start under 2 s, under 200 MB RAM while streaming). On the
maintainer's PC, Smart App Control blocks unsigned executables we build ourselves until code
signing arrives in Phase 9.

## Options

| Option | How it runs | Tray | Size added | Smart App Control in development | Notes |
|---|---|---|---|---|---|
| A. Browser tab | Engine serves the page; user's browser shows it | Separate | ~1 MB of web files | Fine | Not an app window; closing the tab looks like quitting |
| **B. pywebview + WebView2** | Engine serves the page on loopback; a native window shows it with the WebView2 runtime built into Windows | pystray | ~5 MB (plus Pillow) | Fine (checked) | One process, one language for the back end |
| C. PySide6 + Qt WebEngine | Same page inside Qt's bundled Chromium | Qt (have it) | Large: Qt WebEngine ships its own Chromium | Fine | Duplicates a browser Windows already has |
| D. Electron + Python sidecar | Node main process starts the Python engine | Electron | ~100 MB+ runtime | Fine (signed `electron.exe`) | Two runtimes, two processes, highest RAM |
| E. Tauri + Python sidecar | Rust shell starts the Python engine | Tauri | Small | **Blocked**: our own Rust build is unsigned | Needs a Rust toolchain; untestable here until signing |

A quick check on the maintainer's PC (Smart App Control on): a Vite build of React 19,
HeroUI 3 and Tailwind 4 completed, and pywebview opened it from a loopback aiohttp server in
a WebView2 window with a pystray icon alongside. Buttons responded, a WebSocket to the engine
connected, and a warm start to a rendered page took about 1.5 s.

## Decision
Option B.

- **Front end:** React 19 + HeroUI 3 + Tailwind CSS 4, TypeScript, built with Vite, in
  `web/`. HeroUI is built on React Aria, so keyboard and screen-reader support come with the
  components; WebView2 exposes them to Windows UI Automation. End users never need Node: the
  built files ship inside the Python package. Contributors need Node only to change the UI.
- **Host:** the engine process serves the built files and a WebSocket on `127.0.0.1` with a
  random port, using aiohttp (already installed with pyatv). pywebview shows it in a native
  window using Windows' WebView2 runtime. Closing the window keeps Tandem in the tray; the web
  view is destroyed, so background streaming doesn't pay for it.
- **Tray:** pystray (LGPL-3), same menu as today: devices, show window, quit.
- **Contract:** the WebSocket carries the existing `Backend` contract from ADR-0008 as JSON
  messages (device snapshots, events, connect, disconnect, PIN pairing). `DemoBackend` keeps
  running the UI without devices. UI state that needs logic, such as the pairing state machine,
  stays in plain Python and keeps its pytest tests; React renders it.
- **Development:** the same page opens in a normal browser with Vite hot reload against
  `python -m tandem.ui --demo`.
- **Local server safety:** loopback only, so no firewall prompt and nothing on the network.
  A random per-launch token is required, and the server checks the `Host` and `Origin`
  headers, so other web pages and other users' processes can't drive it. Device names reach the
  page only for display; the server logs through `Redactor` (ADR-0007).
- **Look:** one set of design tokens (`web/src/theme.ts`), written as CSS variables for light
  and dark mode, with a test that checks WCAG AA contrast on every background. The window
  background is a setting (theme and background are part of the `Backend` contract as
  `Appearance`): three neutral tones and five colour gradients, drawn by the page, with
  translucent "glass" cards over it.
- **Building on this PC:** Smart App Control can block a native npm binary that is too new to
  have reputation; `web/package.json` pins such packages to a version that loads.
- **Retiring Qt:** the PySide6 + QML shell is removed, along with the `ui` extra's PySide6 and
  qasync dependencies; its ViewModel logic moves to `tandem.ui.controller` with its tests.

## Consequences
- Tandem becomes a web app in a native window: HeroUI's components and animation, and a much
  smaller install than Qt.
- WebView2 is part of Windows 11 and is installed on Windows 10 with Edge; the Phase 9
  installer adds Microsoft's WebView2 bootstrapper for the rare machine without it.
- The UI is now TypeScript, so CI gains a Node job (type check, lint, Vitest, build).
- Licences stay compatible with GPL-3: HeroUI, React, Tailwind, Vite and pythonnet are MIT,
  pywebview is BSD-3, pystray is LGPL-3, and WebView2 is an operating-system component.
- The QML work in Phase 2 is replaced, but its contract, demo backend and ViewModel tests carry
  over.
- Shipping our own `.exe` (Phase 9) is unchanged: Python plus web files either way.
