# ADR-0018: Speaker groups, microphone line-up and the update check

- Status: Accepted
- Date: 2026-11-08

## Context
The maintainer's first hands-on test of 1.0 led to a list of quality-of-life changes (1.2.0).
Three of them shape the architecture: saved sets of speakers, lining speakers up without
fiddling with sliders, and telling people about new versions.

## Decision
- **Groups** live in the engine (`engine/output_groups.py`, `groups.json` next to the output
  preferences). A group is a name and member output ids; it has no stream of its own. The
  window turns members on and off through the `Backend`'s ordinary output calls
  (`ui/groups.py`, shared by the bridge and the demo), and the command services list groups as
  audio targets, so "send audio to <group>" expands to its members.
- **Line-up** (`engine/lineup.py`): for each playing output in turn, `AudioHub.probe` replaces
  the shared source for that output with three 2 kHz beeps (uneven gaps), while
  `adapters/microphone.py` records 16 kHz mono. The pattern's onset, less what was already
  queued for that output, is its lag; every output is delayed to match the slowest. Pure
  Python (no numpy), so it runs in the installed app. Recordings stay in memory. The PC's
  default output is left out: Windows plays it directly and it can't be delayed.
- **Update check** (`ui/updates.py`): one GET of GitHub's releases list when the window opens,
  on by default with a switch in Advanced settings. It never downloads or installs; the window
  links to the release page. No identifiers are sent.

## Consequences
- Line-up depends on the microphone privacy setting; when Windows refuses, the window says
  where to allow it. It needs a quiet room and is untested on hardware at release.
- A group whose members have all gone shows "none of its speakers are around".
- The update check is a second outbound lookup beside App Store icons; the README lists both.
