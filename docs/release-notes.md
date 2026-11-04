# Tandem 1.0.0 (pre-release)

The first full version of Tandem: a Windows app that sends sound and video to Apple TV,
HomePod and AirPlay 2 speakers, and controls them from your PC. It's a **pre-release**: every
feature is built and covered by automated tests, and the installer is built and installed on a
clean Windows machine in CI, but several features haven't been tried on real speakers yet.
Those are listed below. Please [report what you find](https://github.com/CGlover-cmd/tandem/issues).
To attach details, run `"C:\Program Files\Tandem\python\python.exe" -m tandem diagnose`: it
writes a zip of logs with names, addresses and identifiers replaced.

## What's in it

- **Devices:** finds Apple TVs, HomePods and AirPlay 2 speakers; pairs an Apple TV with its two
  PINs; reconnects after Wi-Fi drops.
- **Apple TV remote:** touch pad and arrow keys, Back, Home, play/pause, now playing, volume,
  power, the TV's apps (with real icons), and a keyboard for its text fields.
- **Audio:** the PC's sound to any mix of speakers and the PC's own outputs, each with volume
  and a delay slider to line them up. Or Tandem's own player as the source.
- **Send to TV:** a video file from the PC (MP4 or MOV) or a direct link, with stop.
- **Music:** what any app on the PC is playing, with artwork, controls, a now-playing bar and
  tray controls.
- **Commands (Ctrl+K):** play, pause, next, volume, open an app, turn the TV on or off, send
  audio to speakers, stop streaming.
- **Home app:** optional bridge with Tandem Audio, Tandem Music and Tandem TV switches, for Siri
  on a HomePod and Home automations.
- **Getting started** checklist on first run; light and dark themes; tray menu.

## Checked on real hardware before this release

- Discovery of the Apple TV 4K, two HomePod minis and an AirPlay 2 soundbar.
- Apple TV pairing (both PINs), remote keys, play/pause, now playing, apps and typing.
- The PC's audio to an open-source AirPlay receiver for an hour, bit-exact, with no dropouts.
- Windows' media controls with the Apple Music app (now playing, artwork, play/pause, skip).
- The installed app's window opening on Windows 11 with Smart App Control on (from the app
  folder, not the installer).

## Not yet checked on real hardware (please try these)

1. **Audio to a HomePod mini and the soundbar** from the Audio panel: sound arrives, volume works,
   it survives switching Wi-Fi off and on. A HomePod mini was measured about 5 seconds behind;
   use its delay slider (or raise the others) to line speakers up.
2. **Several speakers at once** staying together for a while, and the delay sliders lining up a
   HomePod with the soundbar.
3. **PC outputs:** with a virtual audio cable as Windows' default, turn on the real speakers in
   the Audio panel and line them up with a HomePod.
4. **Tandem's player** as the source (the Audio panel's "Tandem's player"): a music file and an
   internet radio stream.
5. **Send to TV:** an MP4 from the PC, and a direct video link. Windows may ask to let Tandem
   through the firewall if you used the portable zip.
6. **Home app:** Settings, then "Show Tandem in the Home app", add it in the Home app with the
   code shown, then flip each switch and ask Siri "turn on Tandem Audio".
7. **Commands:** "send audio to <speaker>", "stop streaming", "turn on Tandem Audio".
8. **The installer** on your PC: Start menu shortcut, the firewall rule, the optional startup
   shortcut, and uninstalling.
9. **Wrong PIN** while pairing the Apple TV shows a new PIN and lets you try again.

## Known limits

- **Not code-signed yet.** Windows SmartScreen warns about the installer (choose More info, then
  Run anyway). With **Smart App Control** on, Windows blocks it outright; install with Python
  instead (see the README).
- No screen mirroring (FairPlay; see ADR-0006). No Spotify or Apple Music browsing inside
  Tandem yet: use their apps, and Tandem sends their sound and shows what's playing.
- Windows' volume and mute also affect what Tandem sends (it captures what Windows plays).
- Several speakers are lined up by ear with the delay sliders; there's no automatic sync yet.
- No automatic updates: check the [releases page](https://github.com/CGlover-cmd/tandem/releases).
