# ADR-0023: Lessons from AirParrot

- Status: Accepted
- Date: 2026-11-12

## Context
The maintainer asked what Tandem can learn from AirParrot, a commercial AirPlay sender for
Windows, about talking to devices (research from public sources only: its support pages,
release notes and the community's AirPlay notes, never its binaries). AirParrot uses the same
standard pieces as Tandem: mDNS discovery and AirPlay, on the same network. Its strengths are
practical. It can connect to a receiver by address, it recovers after a network change, its
help pages walk people through the usual network problems, and it supports speaker passwords.

It also asks Windows to let it in on Public networks. The maintainer didn't want Tandem's
"mark this network Private" step (ADR-0017, 1.1.1 addendum), and asked Tandem to do the same
and to build every recommendation.

## Decision
- **Firewall on every network.** Setup adds one allow rule for Tandem's pythonw.exe on every
  profile (`profile=any`), still `remoteip=localsubnet`. The Public block rule, the
  "Is this your network?" note and `tandem.ui.network_trust` are gone. See the ADR-0017
  addendum.
- **Connect by address** (`engine/addresses.py`). Some routers and guest networks drop mDNS.
  The user can type a speaker's private IPv4 address, and if an AirPlay device answers a
  unicast scan there (`pyatv.scan(hosts=...)`), every later scan asks it again. Up to 20
  addresses, saved in `addresses.json` in the data folder. They are private: shown in the
  window, redacted in logs.
- **React to network changes** (`engine/network.py`). Every 3 s the engine reads the PC's
  IPv4 addresses (no admin needed). A change, or a gap of more than 20 s (sleep), triggers a
  rescan. Connections waiting out a backoff then retry at once with the backoff reset, and
  speakers that failed for want of an answer try again.
- **"Can't find a speaker?"** (`engine/net_check.py`). One PowerShell read, with no admin and
  on Windows only, of the adapters that are up, their IPv4 networks and Tandem's firewall
  rule. Together with the last scans, it names the likely cause: offline, a missing firewall
  rule (installed app only), discovery blocked (three empty scans in a row), a speaker on
  another subnet, a VPN, or the Home app's speaker access setting. The report holds codes and
  counts only, and the window holds the words.
- **Silent stalls** (`AudioHub.check_stalls`). pyatv's audio path doesn't report every dead
  connection. A once-a-second watchdog restarts a streaming output whose sender has taken no
  frames for 5 s (30 s after a start). The engine also reconnects that speaker's session, so
  the stream comes back on a fresh connection.
- **Speaker buttons** (`engine/speaker_buttons.py`, `adapters/pyatv_dacp.py`). Tandem gives
  every RTSP session the same `DACP-ID`/`Active-Remote` pair (a hook on pyatv's
  `RtspSession.__init__`, like ADR-0011's). It announces `iTunes_Ctrl_<DACP-ID>` over mDNS
  and serves `/ctrl-int/1/<command>` on a local port. Play, pause and skip go to what the PC
  is playing, or to Tandem's player. Volume keys step that speaker's volume by 5, and a
  reported volume is shown. A request without the token gets 403.
- **Speaker passwords.** pyatv's `pw` flag becomes `Device.password_required`. The window's
  output row asks for the password. It is stored with pyatv's settings in the encrypted vault
  and registered with the redactor. A refused password (`AuthenticationError`) ends a
  connection attempt at once instead of retrying (`session.REFUSALS`), so the row asks again
  without waiting out the 15 s connect timeout, and a wrong password isn't sent over and over.
- **Stereo pairs.** HomePods that share an AirPlay `tsid` are flagged. When one fails to play,
  the row says that a stereo pair only plays from Apple devices and how to ungroup it.
- **Firmware watch.** A monthly job in `dependencies.yml` opens one issue when PyPI has a pyatv
  newer than the pin allows. Apple's updates break senders, and pyatv's fixes come first.
- **Media check** (`media_send.check_playable`). Before a file is sent to the Apple TV,
  Tandem checks its type. For MP4 and QuickTime files it also reads the codecs from the box
  headers. VP8/VP9, AV1, `hev1`/`dvhe`-tagged HEVC, Opus and FLAC give `notPlayable` with
  advice, instead of a failure on the TV.

## Consequences
- On a Public network, such as a café or hotel, other devices on the same subnet can reach
  Tandem's listeners: AirPlay timing while streaming, the media server (token paths) after a
  send, the button server (token header), and the Home bridge if it's on. Nothing from
  outside the subnet can, and the window's server stays loopback-only. The maintainer accepted
  this so that speakers work on any network with no Windows settings to change.
- The button server and its mDNS announcement stay on the local network. No request leaves
  the PC, so the privacy policy needs only a note, not a new switch.
- Unverified on hardware: whether HomePods send DACP to a sender that isn't Apple's (if they
  don't, nothing happens), the `tsid` stereo-pair signal (the reference HomePods aren't
  paired), and the PowerShell read on the maintainer's PC.
- Two pyatv internals are now wrapped (`RtspSession.__init__`, as well as the audio source
  hook). Re-check both when moving the pyatv pin. The tests import the attributes.
