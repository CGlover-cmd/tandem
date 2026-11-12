# Tandem 1.3.0 (pre-release)

A Windows app that sends sound and video to Apple TV, HomePod and AirPlay 2 speakers, and
controls them from your PC. It's still
a **pre-release**: some features haven't been tried on real speakers yet (listed below).
Please [report what you find](https://github.com/CGlover-cmd/tandem/issues). To attach
details, run `"C:\Program Files\Tandem\python\python.exe" -m tandem diagnose`: it writes a zip
of logs with names, addresses and identifiers replaced.

**The installer is still unsigned.** Windows SmartScreen warns about it (choose More info, then
Run anyway), and with Smart App Control on, Windows blocks it: see Known limits below.

## New in 1.3.0

- **Works on any network.** No more marking your Wi-Fi as Private in Windows. Setup's firewall
  rule now covers every network, Private or Public, but only lets in devices on your local
  network, and still nothing from the internet. This replaces 1.1.1's trusted networks and the
  "Is this your network?" note. Install over your current Tandem and setup updates the rule.
- **HomePods play in time.** Tandem now keeps the clock that AirPlay 2 speakers follow (PTP),
  so a HomePod mini no longer runs about 5 seconds behind the other speakers. They play the
  same moment together. Speakers that don't use that clock carry on as before.
- **Cast your screen to the Apple TV.** Press **Screen** on the TV's card, pick which screen
  and a quality, and your PC's screen and sound appear on the TV. It runs a few seconds behind,
  so it suits slides, photos and videos better than games. Stop it from the card or the tray
  menu. This isn't AirPlay screen mirroring, which needs Apple's copy protection; it sends your
  screen as a video stream, only to devices on your home network. It makes the download bigger:
  it brings its own video encoder.
- **Music tab.** Play your own music files (pick the folders, Tandem groups them into albums)
  and internet radio, on any mix of speakers, with no gap between tracks. **Spotify**: see
  your playlists and Spotify devices, search, play on the device you pick and move playback
  between them (Settings, Connections, Spotify; needs Spotify Premium and a free developer key,
  and the walkthrough shows how). **Apple Music**: search the catalogue and open a song or
  album in the Apple Music app.
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
- **Can't find a speaker?** Add a speaker by its address when your router hides it, and let
  Tandem check this PC for the usual causes, such as a VPN, guest Wi-Fi, a router that blocks
  the search, or the Home app's speaker access setting.
- **Back on its own after a network change.** Switching Wi-Fi, plugging in a cable or waking
  the PC makes Tandem look for speakers and reconnect at once. A speaker whose sound stops
  without an error is restarted after a few seconds.
- **Speaker passwords.** A speaker that asks for a password (Home app, Require Password) shows a
  password box in the Audio panel. Tandem keeps it, encrypted.
- **Clearer reasons.** A HomePod that's half of a stereo pair says why it won't play from
  Tandem. A video in a format the Apple TV can't play is caught before it's sent.
- **Your speakers' buttons** (where a speaker sends them) control what the PC plays, and a
  speaker's volume keys change its volume in Tandem.

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
   volume works, it survives switching Wi-Fi off and on, and they play together with no delay
   set (a HomePod mini and the soundbar beeped in time in testing).
3. **Several speakers at once** staying together for a while.
4. **Send to TV:** an MP4 from the PC, and a direct video link.
5. **Home app:** Advanced settings, then "Show Tandem in the Home app", add it in the Home app
   with the code shown, then flip each switch and ask Siri "turn on Tandem Audio".
6. **Commands:** "send audio to <speaker>", "stop streaming", "turn on Tandem Audio".
7. **Your own background photo.**
8. **Line up automatically** with two speakers, then listen: do they play together?
9. **A speaker group**, "send audio to <group>", and the tray's speaker switches.
10. **Ctrl+Alt+K** from another app, and "Turn my speakers back on" after restarting Tandem.
11. **On a Public network** (Windows' setting): speakers appear and play with no prompt.
12. **Can't find a speaker?** Add a speaker by its address, then "Check my network".
13. **Switch Wi-Fi or sleep the PC** while a speaker plays: it comes back on its own.
14. **A HomePod's touch controls** while it plays the PC's sound: do play, pause and skip work?
15. **Cast screen** to the Apple TV: picture and sound arrive, how far behind it runs, and Stop
    from the card and the tray.
16. **Music tab:** a folder of your own music, a radio station, and Spotify sign-in, playlists
    and "Play here".
17. **PC muted while AirPlay plays:** the speakers keep playing (system sounds too), and the PC
    unmutes when they stop.

## Known limits

- **Not code-signed yet.** Windows SmartScreen warns about the installer (choose More info, then
  Run anyway). With **Smart App Control** on, Windows blocks it outright; install with Python
  instead (see the README).
- No AirPlay screen mirroring (FairPlay; see ADR-0006): Cast screen runs a few seconds behind
  and works with the Apple TV only. Apple Music has search and links, not playback inside
  Tandem; the Apple Music app plays it. Spotify needs Premium and plays in Spotify's own apps.
- Windows' volume affects what Tandem sends (it captures what Windows plays).
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
