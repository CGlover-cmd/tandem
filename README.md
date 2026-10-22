# Tandem

Tandem is a free, open-source Windows app for sending audio and video to Apple TV, HomePod
and other AirPlay 2 speakers and TVs, with smart-home control planned later.

> **Status: pre-alpha. Phase 0 research is done ([go/no-go summary](docs/spikes/phase-0-summary.md)).**
> Nothing to install yet. Pairing and remote
> control of Apple TV, streaming audio to HomePod mini and an AirPlay 2 soundbar, and capturing
> the PC's own audio are proven in spikes, as is fast hardware video encoding on NVIDIA GPUs.
> An open-source test receiver on a Raspberry Pi lets audio be checked automatically.
> Screen mirroring was investigated and shelved: it is
> gated by Apple's FairPlay content protection, with no legitimate open-source way to send it
> ([ADR-0006](docs/adr/0006-screen-mirroring-fairplay.md)).
> The core engine (Phase 1) is done: discovery, pairing, connection handling, settings,
> redacted logs and diagnostics, and an encrypted credential store, with a developer
> command-line tool that pairs with and connects to Apple TV, HomePod mini and an AirPlay 2
> soundbar.
> See the [roadmap](docs/ROADMAP.md).

## Goals

- Discover and pair with Apple TV, HomePod and AirPlay 2 receivers on your network
- Apple TV remote control from your PC
- Stream system audio to any mix of AirPlay speakers and your PC's own speakers, in sync
- Send videos and links to Apple TV
- A clean, Apple-inspired interface that's accessible and works from the system tray

Screen mirroring is **not** planned: it is gated by Apple's FairPlay content protection, with no
legitimate open-source way to send it ([ADR-0006](docs/adr/0006-screen-mirroring-fairplay.md)).

## Contributing

Read [docs/PRIVACY.md](docs/PRIVACY.md) before your first commit, then install the hooks:

```
pip install pre-commit
pre-commit install
python tools/build_denylist.py
```

Architecture decisions are recorded in [docs/adr](docs/adr/).

### Development

Tandem needs Python 3.11+ on Windows. Keep the virtualenv outside any synced folder, then
install the package with its development tools:

```
python -m pip install -e ".[dev,ui]"
python -m pytest
python -m ruff check src tests
python -m pyright --pythonpath <path to your venv's python.exe>
```

The developer tool lists AirPlay devices on your network. Names and addresses are replaced
with placeholders such as `<device-1>`, so the output is safe to paste into an issue:

```
python -m tandem discover
python -m tandem watch
python -m tandem pair apple_tv
python -m tandem connect all
python -m tandem forget apple_tv
python -m tandem diagnose
python -m tandem controls apple_tv
python -m tandem remote apple_tv up up select
python -m tandem media apple_tv pause
python -m tandem playing apple_tv --watch 30
python -m tandem volume apple_tv up
```

`pair`, `connect` and `forget` take a target: `all`, a kind (`apple_tv`, `homepod`, `receiver`),
part of a model name, or a device's own name. `pair` asks for each PIN the device shows;
`connect` connects, stays connected for a few seconds and disconnects (`--keep` stays connected
and reconnects after drops until Ctrl+C). `diagnose` writes a zip of logs and device details
with names, addresses and identifiers replaced, for attaching to a bug report; it never
includes pairing credentials.

The Apple TV commands connect, act and disconnect. `controls` lists what the device can do right
now (it changes with what's playing). Media titles are hidden unless `--show-private` is given.
An Apple TV that changes the TV's volume by infrared (its Volume Control setting) can't have
its volume changed from Tandem; `volume` says so.

Settings, the encrypted credential store and logs live in `%LOCALAPPDATA%\Tandem`.

### Preview the interface

The interface is in early development. It's a [HeroUI](https://heroui.com) (React) front end that
Tandem shows in its own window, using the WebView2 engine built into Windows. Build it once with
[Node.js](https://nodejs.org) 20 or later, then run it. It shows the AirPlay devices on your
network; add `--demo` to see invented devices instead (no network needed):

```
npm --prefix web install
npm --prefix web run build
python -m tandem.ui
python -m tandem.ui --demo
```

Choose **Pair** on an Apple TV and type in the PIN it shows. An Apple TV asks twice: once for
remote control and once for AirPlay. Once a device is connected, **Remote** opens its controls:
a touch pad (or the arrow keys, Enter and Backspace), Back, Home, what's playing, and volume.
On an Apple TV, **Apps** lists its apps (with a search box) and opens the one you pick, and
**Keyboard** types into the TV's text field. The keyboard opens by itself when the TV asks for
text, such as in a search box.

App icons are looked up on the App Store the first time the list opens and kept on this PC
([ADR-0012](docs/adr/0012-app-icons-from-the-app-store.md)). This tells Apple which apps are on
the TV; turn off **App icons** in Settings to show letters instead.

Close the window to send it to the tray; choose **Quit Tandem** from the tray menu to exit.
Pick a theme and a window background (neutral tones or gradients) under **Settings**, the gear
button at the top right.

To work on the interface with hot reload, run the app without its window, start the Vite dev
server, and open the dev-server address the app prints:

```
python -m tandem.ui --demo --no-window --port 8765 --dev-origin http://localhost:5173
npm --prefix web run dev
```

Front-end checks: `npm --prefix web run typecheck` and `npm --prefix web test` (the tests include
WCAG AA contrast checks for every colour on every background).

## Legal

Licensed under GPL-3.0-or-later. This is an independent project, not affiliated with or endorsed
by Apple Inc. Apple TV, HomePod, AirPlay and HomeKit are trademarks of Apple Inc., used here only
to describe compatibility.
