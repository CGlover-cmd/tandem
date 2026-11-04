# ADR-0016: Tandem as a Home app bridge

- Status: Accepted
- Date: 2026-11-04

## Context
ADR-0014 rules out talking to Siri from Windows and plans step 10b instead: Tandem shows up in
the Home app, so Siri on a HomePod and Home automations can drive it. That needs a HomeKit
accessory server (HAP) on the PC.

## Decision
- **HAP-python** (Apache-2.0, works with our GPL-3 licence) runs the accessory server inside
  Tandem's own asyncio loop, on TCP port 51827. It loads under Smart App Control.
- **Off by default.** Settings has one switch, "Show Tandem in the Home app". While it's on and
  not yet added, Settings shows the 8-digit setup code; HAP-python's own console print of the
  code is silenced.
- **Three fixed switches:** Tandem Audio (send the PC's sound to the outputs used last, or to
  every speaker that needs no PIN), Tandem Music (Tandem's player), Tandem TV (the paired Apple
  TV's power). Generic names mean no device or room name leaves the PC. Each switch follows
  Tandem's state back into the Home app. The command bar can flip them too ("turn on tandem
  audio").
- **Keys stay private:** HAP-python's state file (the bridge identity and the Home app's
  pairing keys) is encrypted with DPAPI (`adapters/hap_bridge.py`), like the credential vault
  (ADR-0007).

## Consequences
- Windows Firewall must allow inbound TCP 51827 on private networks; the installer adds the
  rule. Without it the Home app finds Tandem but can't add it.
- Siri can only say what the Home app can: "turn on Tandem Audio", not "play jazz on Tandem".
- Hardware-untested at release: adding the bridge in the Home app and flipping each switch is
  on the release checklist. Direct control of other accessories (10d) is not built.
