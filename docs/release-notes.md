# Tandem 1.2.1 (pre-release)

A Windows app that sends sound and video to Apple TV, HomePod and AirPlay 2 speakers, and
controls them from your PC. It's still
a **pre-release**: some features haven't been tried on real speakers yet (listed below).
Please [report what you find](https://github.com/CGlover-cmd/tandem/issues). To attach
details, run `"C:\Program Files\Tandem\python\python.exe" -m tandem diagnose`: it writes a zip
of logs with names, addresses and identifiers replaced.

## Coming next (not released yet)

- **Cast your screen to the Apple TV.** Press **Screen** on the TV's card, pick which screen
  and a quality, and your PC's screen and sound appear on the TV. It runs a few seconds behind,
  so it suits slides, photos and videos better than games. Stop it from the card or the tray
  menu. This isn't AirPlay screen mirroring, which needs Apple's copy protection; it sends your
  screen as a video stream, only to devices on your home network. It makes the download bigger:
  it brings its own video encoder.
- **Audio and Video buttons on every card.** Press **Audio** to play your PC's sound on that
  device, or press it again to stop. You don't need to visit the Audio panel. Apple TVs also get
  **Video**, which sends a video file or link. An unpaired device pairs first, then carries on.
  These replace the Pair, Connect and Send buttons.
- **A speaker's remote is audio only:** play, pause, skip back and forward, and volume. There's
  no touch pad any more. While the speaker plays your PC's sound, the buttons control the app
  playing on your PC.
- **Your PC goes quiet while AirPlay plays.** Tandem mutes Windows' default output while your
  speakers play the PC's sound, so there's no echo, and unmutes it when they stop. Turn the
  PC's switch on in the Audio panel to hear both (the PC plays a little ahead), or turn this off
  in Advanced settings. No virtual audio cable needed for that any more.

## Fixed in 1.2.1

- **The window opens again.** In 1.2.0 the window never appeared: a "Python" process ran in
  Task Manager, and every later launch quietly did nothing. Install 1.2.1 over it. If Tandem's
  window ever fails to open again, it now says so and closes, instead of staying stuck.
- **Installing over a running Tandem just works.** Setup asks Tandem to close (and closes
  older copies itself), installs, and opens it again, with no "unable to close applications"
  prompt. Uninstalling closes it too.
- **Window polish:** icons at their real size, clearer row titles in sheets, card buttons
  that wrap on a narrow window, quieter scrollbars and sliders, a remote that fits without
  scrolling, and one close button per sheet.

## New in 1.2.0

- **Line up automatically** (Settings, Advanced settings): Tandem plays three short beeps on
  each playing speaker in turn, listens with the PC's microphone, and sets the delays so they
  play together. Pause your music first. Windows must let desktop apps use the microphone.
- **Speaker groups:** with two or more speakers playing, "Save these speakers as a group" in
  the Audio panel. A group has one switch, and the command bar understands "send audio to
  <group>".
- **All speakers** volume slider in the Audio panel: moves every playing speaker together.
- **Turn my speakers back on** (Advanced settings): the speakers you left on play again when
  Tandem starts.
- **Speakers in the tray menu:** a switch for each one, so the window rarely needs opening.
- **Ctrl+Alt+K anywhere in Windows** opens Tandem with its commands ready.
- **Clearer speaker errors:** a failed speaker says why (no answer, turned away by the Home
  app's speaker access setting, or an untrusted network) and how to fix it.
- **Update check:** when a newer Tandem is out, the window says so and links to it. One look at
  GitHub's releases list at start; turn it off in Advanced settings.
- **Report a problem** (Advanced settings or the tray): saves the diagnostics file, shows it,
  and opens a GitHub issue for you to describe the problem and attach it.
- **Photo background blur** (Settings, under your photo).
- **Faster to open:** setup prepares Tandem's libraries once, instead of on every start. The
  download is smaller too.
- **Quieter when idle:** while the window is hidden and nothing plays, Tandem looks for devices
  once a minute instead of every few seconds.

Media keys need nothing from Tandem: Windows already sends them to the app that's playing.

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
8. **Line up automatically** with two speakers, then listen: do they play together?
9. **A speaker group**, "send audio to <group>", and the tray's speaker switches.
10. **Ctrl+Alt+K** from another app, and "Turn my speakers back on" after restarting Tandem.

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
- Automatic line-up needs a microphone and a quiet room, and leaves the PC's own speakers as
  they are (Windows plays them directly).
- Tandem tells you about updates but doesn't install them: download the new setup from the
  [releases page](https://github.com/CGlover-cmd/tandem/releases).

## Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by
[SignPath Foundation](https://signpath.org). Until the first signed release, the installer is
unsigned. Tandem has one maintainer, [CGlover-cmd](https://github.com/CGlover-cmd), who is its
committer, reviewer and approver. Tandem sends nothing about you or your PC to anyone, apart
from two lookups you can turn off: see the
[privacy policy](https://github.com/CGlover-cmd/tandem/blob/main/docs/privacy-policy.md).
