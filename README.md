# Tandem

**AirPlay for your Windows PC.** Play your PC's sound on your HomePods and AirPlay speakers,
and control your Apple TV from your desktop.

Tandem is a free, open-source Windows app. Switch on a speaker in Tandem and whatever your PC
is playing (Spotify, Apple Music, a podcast in your browser) comes out of it straight away. Use
one speaker or the whole house: Tandem plays them all together, in time, from one volume
slider. Your Apple TV gets a remote on your desktop, with a keyboard for those search boxes.

There's nothing else to buy or set up. Tandem talks straight from your PC to your devices over
your home Wi-Fi: no extra box, no account, no sign-up, and nothing collected about you.

**[Download Tandem](https://github.com/CGlover-cmd/tandem/releases/latest)** ·
[What's new in 1.3.0](docs/release-notes.md) ·
[Report a bug](https://github.com/CGlover-cmd/tandem/issues)

> **Tandem 1.3.0 is a pre-release.** Everything below is built and tested in code, but a few
> features haven't been tried on real speakers yet; the [release notes](docs/release-notes.md)
> list which. If something doesn't work, please
> [tell us](https://github.com/CGlover-cmd/tandem/issues).

## What you can do

- **Play your PC's sound on any AirPlay speaker.** HomePod, HomePod mini, AirPlay 2 speakers,
  soundbars, AirPlay TVs and the Apple TV. Switch a speaker on and it plays; switch it off and
  it stops.
- **Fill the house with music.** Play to any mix of speakers at once, plus your PC's own
  headphones or speakers, each with its own volume and an **All speakers** slider for the lot.
  Save your favourite combinations as groups ("Downstairs", "Everywhere").
- **Keep every speaker in sync.** **Line up automatically** plays a few short beeps, listens
  with your PC's microphone and sets each speaker's delay so they play together.
- **Control your Apple TV.** A touch pad, Back and Home, play and pause, what's playing,
  volume, power, your TV's apps, and a keyboard that pops up when the TV asks for text.
- **Send a video to the TV.** Play a video file from your PC, or a link to one, on the Apple TV.
  Tandem tells you before sending if the TV can't play the file's format.
- **Use your speakers' own buttons.** Where a speaker sends them, its play, pause, skip and
  volume buttons control what your PC is playing.
- **Show your screen on the TV.** **Cast screen** puts your PC's screen, with its sound, on the
  Apple TV. The picture runs a few seconds behind, so it suits slides, photos and videos better
  than games. (Not released yet.)
- **Control your music.** See and control what any app on your PC is playing (Spotify, Apple
  Music, a browser tab), from Tandem's window or the system tray.
- **Play your own music and the radio.** Tandem plays the albums in your music folders (MP3,
  FLAC, WAV, Ogg) and thousands of free internet radio stations straight to your speakers, with
  a queue. Search Apple Music's catalog and open what you find in the Apple Music app, and use
  Tandem as a remote for Spotify on any of your devices.
- **Just type what you want.** Press Ctrl+K and type "pause", "volume 30 on the loft",
  "send audio to the patio" or "open Music on the TV". Ctrl+Alt+K does it from anywhere in
  Windows.
- **Use Siri and the Home app.** Tandem can appear in Apple's Home app as three switches, so
  you can say "Hey Siri, turn on Tandem Audio" to a HomePod or build it into your automations.

## What you need

- A PC with **Windows 11**, or **Windows 10 22H2** or later (64-bit).
- At least one **Apple TV, HomePod or AirPlay 2 speaker or TV** on the same home network.

That's all. You don't need a Mac or any extra hardware.

**What Tandem doesn't do:** it can't use AirPlay screen mirroring, the instant kind an iPhone
does. Apple protects it with its FairPlay copy protection, and Tandem won't work around that
([why](docs/adr/0006-screen-mirroring-fairplay.md)). **Cast screen** sends your screen as a
video stream instead, a few seconds behind. Tandem also can't make your PC into an
AirPlay speaker for your iPhone, and it doesn't support Chromecast.

## Install

1. Download `Tandem-<version>-setup.exe` from the
   [latest release](https://github.com/CGlover-cmd/tandem/releases/latest).
2. Run it. Windows may warn that the publisher is unknown, because Tandem isn't code-signed yet.
   Choose **More info**, then **Run anyway**. That's the only prompt. The installer lets your
   speakers and TV reach Tandem on networks you trust (see
   [Network and security](#network-and-security)), and installs Microsoft's WebView2 if your PC
   doesn't have it.
3. Open **Tandem** from the Start menu.

**If Windows blocks the installer outright:** that's Smart App Control, which blocks every
unsigned installer and has no "allow" button. Until Tandem is signed, install it with Python
instead: get Python 3.11 or later from python.org, then run
`py -m pip install "tandem[ui] @ <link to the .whl file on the release page>"` and start it with
`pyw -m tandem.ui`.

A portable zip (no installer, no firewall rule) is on the release page too: unzip it and run
`python\pythonw.exe -m tandem.ui` from the folder.

## Getting started

When Tandem opens, it finds the AirPlay devices on your network by itself, and a short
**Getting started** checklist walks you through the first steps.

- **Speakers:** press **Audio** on a speaker's card (or switch it on in the **Audio** panel).
  Whatever your PC plays now goes there too. Its **Remote** is audio only: play, pause, skip
  back and forward, and volume. While the speaker plays your PC's sound, those buttons control
  the app on your PC.
- **Apple TV:** press **Audio** to use it as a speaker, **Video** to send it a video file or
  link, or **Screen** to cast your PC's screen to it (pick the screen, the quality and whether
  the sound goes too; **Stop casting** is also in the tray menu). The first time, Tandem pairs it: type the PIN the TV shows. It asks twice, once for the
  remote and once for AirPlay. **Remote** opens its controls: the touch pad (or your
  arrow keys, Enter and Backspace), Back, Home, what's playing and volume. **Apps** opens any app
  on the TV, and **Keyboard** types into the TV's search boxes.
- **Music:** the **Music** tab shows what's playing on your PC with its artwork, and lets you
  play, pause, skip and (where the app allows) seek. A small now-playing bar does the same on
  the other tabs. Tandem is the remote here: Spotify or Apple Music still plays the music, and
  Tandem sends the sound to your speakers.
  Tandem also plays music itself: **This PC** lists the albums in folders you add, **Radio**
  searches the free [Radio Browser](https://www.radio-browser.info) directory and keeps the
  stations you save, and **Queue** shows what plays next. **Apple Music** searches Apple's
  catalog (no account needed) and opens a song or album in the Apple Music app, where you press
  play. Only your search words go to the radio directory or to Apple.
  **Spotify** shows your playlists and Spotify devices, searches Spotify, plays on the device
  you pick and moves playback between devices ("Play here"); the Spotify app plays the music.
  Set it up once under **Settings → Connections → Spotify**: Spotify asks each app to use its
  own free developer key, so the walkthrough has you create one in Spotify's developer
  dashboard, paste its Client ID and sign in in your browser. Spotify allows this only with
  Spotify Premium. Your sign-in stays on this PC, encrypted for your Windows account.
- **Commands:** press **Ctrl+K** and type. The line under the box says what Enter will do.
  Names can be partial ("loft", "liv") and forgive small typos; if a command could mean more
  than one device, Tandem asks which.

  ```
  pause
  next on the patio
  volume 30 on loft
  set the den soundbar volume to 20
  louder
  send audio to downstairs
  open Music on the TV
  turn off the TV
  help
  ```

Closing the window sends Tandem to the system tray, where each speaker has its own switch.
Choose **Quit Tandem** from the tray menu to exit. **Settings** (the gear at the top right)
holds the theme and window background. **Advanced settings** there holds speaker delays and
automatic line-up, turning your speakers back on at start, muting the PC while AirPlay plays,
the Home app switches, and the update check.

**Your PC's own speakers:** while AirPlay plays your PC's sound, Tandem mutes Windows' default
output, because AirPlay plays a moment later and hearing both sounds like an echo. It unmutes
when the speakers stop. To hear the PC too, turn its switch back on in the Audio panel (it plays
a little ahead of AirPlay), or turn the muting off in Advanced settings
([details](docs/adr/0020-mute-the-pc-while-airplay-plays.md)). Headphones or another output you
turn on in the Audio panel play in step with AirPlay. To hear the PC's main speakers in step,
install a virtual audio cable such as [VB-CABLE](https://vb-audio.com/Cable/), make it Windows'
default output, then switch your real PC speakers on in the Audio panel
([details](docs/adr/0005-multi-output-audio-routing.md)).

**Siri and the Home app:** turn on **Show Tandem in the Home app** in Advanced settings and add
it in the Home app with the 8-digit code Tandem shows. It appears as three switches (Tandem
Audio, Tandem Music, Tandem TV). Tandem can't talk to Siri directly, because Windows has no
supported way to ([details](docs/adr/0014-commands-no-siri.md),
[Home bridge](docs/adr/0016-home-bridge.md)).

## Your privacy

Tandem doesn't collect anything or send anything anywhere except to your own devices, with two
small exceptions you can turn off in Advanced settings:

- **App icons:** the first time you open your TV's app list, Tandem looks up the icons on the
  App Store, which tells Apple which apps are on the TV
  ([details](docs/adr/0012-app-icons-from-the-app-store.md)). Turn off **App icons** to show
  letters instead.
- **Update check:** when the window opens, Tandem checks GitHub's releases list for a newer
  version.

The recordings made by **Line up automatically** stay in memory and are thrown away as soon as
the beeps are timed. The installer asks about both lookups, and the full
[privacy policy](docs/privacy-policy.md) lists exactly what is sent and to whom.

## Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by
[SignPath Foundation](https://signpath.org).

- **Until the first signed release, the installer is unsigned.** Windows may warn about it, and
  Smart App Control blocks it; the Python install above works around that.
- **Roles:** Tandem has one maintainer, [CGlover-cmd](https://github.com/CGlover-cmd), who is
  the committer, reviewer and approver. Every signing request is approved by hand, and only
  installers built from a tagged release by this repository's
  [GitHub Actions workflow](.github/workflows/release.yml) are submitted for signing
  ([how it works](docs/signing.md)).
- **Privacy:** Tandem sends nothing about you or your PC to anyone, apart from two lookups you
  can turn off, in the installer or in Settings. See the
  [privacy policy](docs/privacy-policy.md).

## Network and security

Tandem works on any network, Private or Public, with nothing to change in Windows. The
installer adds one firewall rule for Tandem itself: devices on your **local network** (the same
Wi-Fi or router as your PC) may reach it, and nothing from the internet can. Devices on the
same network can reach:

- **Tandem's window** never: it listens on this PC only (127.0.0.1) and needs a per-launch key.
- **While audio is streaming:** the AirPlay timing and control ports pyatv opens. A device on the
  same Wi-Fi could at most disturb that stream.
- **Your speakers' own buttons:** a small server that takes play, pause, skip and volume from
  your speakers. It only accepts requests that carry the secret Tandem gave the speaker.
- **Once you've sent a video to the TV or cast your screen:** a small file server, until Tandem
  quits. It hands out only the files you sent, and the live screen stream only while you cast,
  each at an address with a random secret in it, and it answers devices on your home network
  only.
- **The Home app bridge** (off unless you turn it on): Apple's HomeKit protocol, encrypted, and
  it pairs only with the 8-digit code shown in Tandem's window.

The remaining risk is the usual one for any app that listens on a network: a bug in Tandem or a
library it uses could be found by someone on the same Wi-Fi. On a shared network (a café, a
hotel), quit Tandem when you're not using it
([details](docs/adr/0023-lessons-from-airparrot.md)).

**Can't find a speaker?** Open it from the device list, the Audio panel or Settings.
- **Add a speaker by its address:** some routers and guest networks hide speakers from the
  search. Find the speaker's address in your router's list of devices, type it in, and Tandem
  asks it directly from then on.
- **Check my network:** looks at this PC for the usual causes and says what to change:
  - a VPN that's on
  - a speaker on guest Wi-Fi
  - a router that blocks the search
  - a missing firewall rule
  - the Home app's speaker access setting

Tandem also notices when your PC changes networks or wakes from sleep, and looks for your
speakers again at once.

## Help and bug reports

Found a bug or have an idea? [Open an issue](https://github.com/CGlover-cmd/tandem/issues).
**Report a problem** (in Advanced settings or the tray menu) does most of the work: it saves a
diagnostics file with your device names, addresses and identifiers replaced, and opens a new
issue for you to describe what happened and attach it.

## Contributing

Tandem is built in Python on [pyatv](https://github.com/postlund/pyatv), with a
[HeroUI](https://heroui.com) (React) interface shown in a WebView2 window. Contributions are
welcome. Read [docs/PRIVACY.md](docs/PRIVACY.md) before your first commit, then install the
hooks:

```
pip install pre-commit
pre-commit install
python tools/build_denylist.py
```

The plan and status are in [docs/ROADMAP.md](docs/ROADMAP.md), and architecture decisions are
recorded in [docs/adr](docs/adr/).

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

### Run the interface from source

Build the front end once with [Node.js](https://nodejs.org) 20 or later, then run it. It shows
the AirPlay devices on your network; add `--demo` to see invented devices instead (no network
needed):

```
npm --prefix web install
npm --prefix web run build
python -m tandem.ui
python -m tandem.ui --demo
```

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
