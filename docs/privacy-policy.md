# Tandem privacy policy

Tandem is a free, open-source Windows app. It has no accounts, no ads and no telemetry, and it
doesn't send anything about you or your PC to the Tandem project or to anyone else's server
that Tandem runs. This page says exactly what leaves your PC, and how to stop it.

(Contributors: the rules for people who work on Tandem are in [PRIVACY.md](PRIVACY.md).)

## Stays on your network

Tandem talks to the AirPlay devices on your home network (Apple TVs, HomePods, speakers and
TVs). What your PC plays, your remote-control presses and your pairing codes go to those
devices and nowhere else. Pairing credentials and speaker passwords are stored on your PC,
encrypted for your Windows account.

So that your speakers' own buttons can reach it, Tandem announces a remote-control service on
your local network (mDNS, the way iTunes did). The announcement carries a random identifier
made for each run and nothing about you. **Check my network** reads this PC's network adapters
and firewall rule, and leaves the PC with nothing.

## Two optional lookups on the internet

Both are **on by default**, and you can turn either one off during setup (the installer asks)
or later in Tandem's **Settings, Advanced settings**.

| Lookup | When | What is sent | Who receives it |
| --- | --- | --- | --- |
| **App icons** | The first time you open an Apple TV's app list | The bundle identifiers of the apps on your TV (for example `com.netflix.Netflix`), so Tandem can fetch their icons | Apple's App Store lookup service (itunes.apple.com), under [Apple's privacy policy](https://www.apple.com/legal/privacy/) |
| **Update check** | When Tandem's window opens | Nothing about you or your PC. Tandem asks for GitHub's list of Tandem releases | GitHub (api.github.com), under [GitHub's privacy statement](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement) |

Both receivers can see your PC's internet address, as with any web request. Tandem doesn't
send your name, your device names, what you play or anything else. If you turn **App icons**
off, Tandem shows letters instead of icons. If you turn the **Update check** off, Tandem never
contacts GitHub; you can still look for new versions on the
[releases page](https://github.com/CGlover-cmd/tandem/releases).

## Things you start yourself

- **Send to TV with a link:** the Apple TV, not your PC, fetches the video from the address
  you gave. The website sees the TV's request.
- **Home app bridge** (off unless you turn it on): speaks Apple's HomeKit protocol with devices
  on your own network, encrypted.
- **Report a problem:** Tandem saves a diagnostics file on your PC, with device names,
  addresses and identifiers already replaced, and opens a GitHub issue page. Nothing is sent
  until you attach the file and submit the issue yourself.

## Installing

The installer includes Microsoft's WebView2 bootstrapper and runs it only if your PC doesn't
already have WebView2 (Windows 11 does). Microsoft's installer downloads WebView2 from
Microsoft under [Microsoft's privacy statement](https://privacy.microsoft.com/privacystatement).

## What Tandem keeps on your PC

Settings, saved speakers and groups, speaker addresses you added, your pairing credentials
and short logs, all under
`%LOCALAPPDATA%\Tandem`. Logs and diagnostics replace names, addresses and identifiers with
placeholders, and never contain pairing credentials, what's playing or the commands you type.
The recordings made by **Line up automatically** stay in memory and are thrown away as soon as
the beeps are timed. Uninstalling Tandem removes the program; delete that folder to remove
your data too.

## Contact

Questions or concerns: [open an issue](https://github.com/CGlover-cmd/tandem/issues).
