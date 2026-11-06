# Tandem

Tandem is a free, open-source Windows app for sending audio and video to Apple TV, HomePod
and other AirPlay 2 speakers and TVs, and for controlling them from your PC.

> **Status: 1.0.0, a pre-release.** Every feature below is built and tested in code, but some
> haven't been checked on real speakers yet; the [release notes](docs/release-notes.md) list
> which. Please [report bugs](https://github.com/CGlover-cmd/tandem/issues).

## What it does

- **Finds your devices** on the network: Apple TV, HomePod and AirPlay 2 speakers, soundbars
  and TVs. A short **Getting started** checklist walks you through the first steps.
- **Apple TV remote:** a touch pad, Back and Home, play and pause, what's playing, volume,
  power, your TV's apps, and a keyboard for its search boxes.
- **Audio:** sends whatever the PC plays to any mix of speakers at once, plus the PC's own
  outputs (headphones, a second sound card), each with its own volume and a delay to line
  them up by ear.
- **Send to TV:** plays a video file from the PC, or a link to a video, on the Apple TV.
- **Music:** shows and controls what any app on the PC is playing (Spotify, Apple Music, a
  browser), with a now-playing bar and tray controls. Tandem is a remote for the streaming
  apps; their sound reaches your speakers through Tandem's audio
  ([ADR-0013](docs/adr/0013-music-integration-boundaries.md)).
- **Commands:** press Ctrl+K and type "pause", "volume 30 on the loft", "send audio to the
  patio" or "open Music on the TV".
- **Home app:** turn on "Show Tandem in the Home app" in Settings and Tandem appears there as
  three switches (Tandem Audio, Tandem Music, Tandem TV), so Siri on a HomePod and your Home
  automations can drive it ([ADR-0016](docs/adr/0016-home-bridge.md)). Tandem can't talk to
  Siri directly; there's no supported way from Windows
  ([ADR-0014](docs/adr/0014-commands-no-siri.md)).

Screen mirroring is **not** included: it is gated by Apple's FairPlay content protection, with
no legitimate open-source way to send it ([ADR-0006](docs/adr/0006-screen-mirroring-fairplay.md)).
Nothing is collected or sent anywhere except to your own devices (and, if you leave app icons
on, an App Store icon lookup).

## Install

Tandem runs on Windows 11 and Windows 10 22H2 or later (64-bit).

1. Download `Tandem-<version>-setup.exe` from the
   [latest release](https://github.com/CGlover-cmd/tandem/releases).
2. Run it. Windows may warn that the publisher is unknown: Tandem isn't code-signed yet. Choose
   **More info**, then **Run anyway**. The installer adds a Windows Firewall rule so your
   speakers and TV can reach Tandem on private networks, and installs Microsoft's WebView2 if
   your PC doesn't have it.
3. Open **Tandem** from the Start menu.

**Smart App Control:** if it's on, Windows blocks unsigned installers outright, including
Tandem's, and Windows won't let you allow one. Until Tandem is signed, install it with Python
instead: get Python 3.11 or later from python.org, then run
`py -m pip install "tandem[ui] @ <link to the .whl file on the release page>"` and start it with
`pyw -m tandem.ui`.

A portable zip (no installer, no firewall rule) is on the release page too: unzip it and run
`python\pythonw.exe -m tandem.ui` from the folder.

**For in-sync PC speakers:** while Tandem sends the PC's own sound, it can't also play it on
the speakers it's capturing (that would echo). Install a virtual audio cable such as
[VB-CABLE](https://vb-audio.com/Cable/), set it as Windows' default output, then turn your real
speakers on in Tandem's Audio panel ([ADR-0005](docs/adr/0005-multi-output-audio-routing.md)).

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
python -m tandem stream homepod --nth 1 --volume 30
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

`stream` sends whatever the PC is playing to one device until Ctrl+C (or `--seconds`), and
prints how much audio went out. If the connection drops it picks up again when the device
reconnects. For now the PC's own speakers keep playing too, and turning the PC's volume down
also turns the stream down.

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

Press **Ctrl+K** (or choose **Commands** at the top) to type a command. As you type, the line
under the box says what Enter will do:

```
pause
next on the patio
volume 30 on loft
set the den soundbar volume to 20
louder
open Music on the TV
turn off the TV
help
```

Device names can be partial ("loft", "liv") and forgive small typos. When a command could
mean more than one device, Tandem asks which and lists the choices; pick one with the arrow
keys and Enter. "send audio to ..." and "stop streaming" will work once audio streaming lands.

The **Music** tab shows what any app on this PC is playing (Spotify, Apple Music, a browser
tab), with its artwork, and lets you play, pause, skip and, where the app allows, seek. On the
other tabs a small now-playing bar does the same; the tray menu has play/pause and next. Tandem
is a remote here: the app plays the music, and Tandem's audio streaming sends the PC's sound to
your speakers.

Tandem also plays music itself. In the Music tab, **This PC** lists the albums in folders you
add (MP3, FLAC, WAV and Ogg files), with artwork, artists and a song search; **Radio** searches
the free [Radio Browser](https://www.radio-browser.info) directory and keeps the stations you
save; **Queue** shows what plays next. Pick the speakers in **Audio**: Tandem's player plays
straight to them, gaplessly. Only your search words go to the radio directory.

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
