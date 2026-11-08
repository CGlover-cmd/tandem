# Tandem 1.1.1 (pre-release)

A Windows app that sends sound and video to Apple TV, HomePod and AirPlay 2 speakers, and
controls them from your PC. It's still
a **pre-release**: some features haven't been tried on real speakers yet (listed below).
Please [report what you find](https://github.com/CGlover-cmd/tandem/issues). To attach
details, run `"C:\Program Files\Tandem\python\python.exe" -m tandem diagnose`: it writes a zip
of logs with names, addresses and identifiers replaced.

## New in 1.1.1

- **One prompt to install.** On a network Windows marks as Public (often home Wi-Fi), 1.1.0
  also asked "allow Python through the firewall?" the first time Tandem opened. That prompt is
  gone.
- **Trusted networks.** Tandem now uses Windows' own Private/Public setting, which Windows
  remembers for each network. On Private networks your speakers and TV can reach Tandem; on
  Public ones Tandem stays closed, and the window shows "Is this your network?" with a button
  to Windows' network settings, where you mark it Private. If your home Wi-Fi is set to Public,
  you'll see this note once after installing.

## Fixed in 1.1.0

- **Apple TV pairing said "That PIN didn't match" even with the right PIN.** The 1.0.0
  installer picked up a newer version of a library (srptools 2.0) that broke the handshake
  Apple devices use. The installer now ships the exact library versions Tandem was tested
  with, and a test checks that handshake on every change.
- **HomePods wouldn't connect and the soundbar kept reconnecting.** Same cause. Checked after
  the fix: the PC's sound streamed to a HomePod mini and the soundbar with no errors.
- **A speaker that couldn't be reached was retried forever** in the background. Tandem now
  gives up after 15 seconds, says so, and stops trying.
- **"2 playing" when only the PC was playing.** A speaker that failed was counted. The count
  now shows only the speakers Tandem is sending to.

## Changed in 1.1.0

- **Audio panel:** a spinner shows next to a speaker's switch the moment you turn it on. The
  panel says what the switch does: the PC's sound plays there right away, nothing else to
  press. Windows' own output (your laptop speakers, say) is listed as on, since Windows keeps
  playing there.
- **One source:** the "This PC / Tandem's player" choice is gone. Tandem sends everything the
  PC plays.
- **Advanced settings** (Settings, then Advanced settings): the speaker delays, the App Store
  icon lookup and the Home app bridge moved here.
- **Getting started:** the Apple TV step has a **Pair** button.
- **Backgrounds:** Sky is the new default, and you can use a photo of your own (Settings,
  Background, Choose a photo). Tandem keeps a resized copy, without the photo's location and
  camera details.
- Setup shows Tandem's name and version in Windows, and always opens Tandem as you, not as
  administrator.

## Not yet checked on real hardware (please try these)

1. **Apple TV pairing** with both PINs, and a wrong PIN (it should show a new PIN to try).
2. **Audio to both HomePod minis and the soundbar** from the Audio panel: sound arrives,
   volume works, it survives switching Wi-Fi off and on. A HomePod mini was measured about 5
   seconds behind; use its delay in Advanced settings (or delay the others) to line them up.
3. **Several speakers at once** staying together for a while.
4. **Send to TV:** an MP4 from the PC, and a direct video link.
5. **Home app:** Advanced settings, then "Show Tandem in the Home app", add it in the Home app
   with the code shown, then flip each switch and ask Siri "turn on Tandem Audio".
6. **Commands:** "send audio to <speaker>", "stop streaming", "turn on Tandem Audio".
7. **Your own background photo.**

## Known limits

- **Not code-signed yet.** Windows SmartScreen warns about the installer (choose More info, then
  Run anyway). With **Smart App Control** on, Windows blocks it outright; install with Python
  instead (see the README).
- On a Public network Tandem can't find or reach your speakers until you trust the network.
- No screen mirroring (FairPlay; see ADR-0006). No Spotify or Apple Music browsing inside
  Tandem yet: use their apps, and Tandem sends their sound and shows what's playing.
- Windows' volume and mute also affect what Tandem sends (it captures what Windows plays), and
  Windows keeps playing on its own output too. To hear only your speakers, set a virtual audio
  cable as Windows' default output.
- The Home app gets three switches, not all of Tandem: choosing speakers, volume and the remote
  stay in Tandem's window.
- Speakers are lined up by ear with the delays; there's no automatic sync yet.
- No automatic updates: check the [releases page](https://github.com/CGlover-cmd/tandem/releases).
