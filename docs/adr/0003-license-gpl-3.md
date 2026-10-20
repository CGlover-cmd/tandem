# ADR-0003: Licence: GPL-3.0-or-later

- Status: Accepted
- Date: 2026-10-20

## Context
The project is free for everyone to use. The most useful open-source reference code for
mirroring and AirPlay 2 audio (e.g. UxPlay, shairport-sync, OwnTone) is GPL-licensed. Our main
dependencies are permissive or LGPL (pyatv: MIT, PySide6: LGPL, FFmpeg/PyAV: LGPL builds).

## Decision
License the project under the GNU General Public License v3.0 or later.

## Consequences
- Anyone may use, study, modify and share the app; anyone who distributes a modified version
  must share its source too, so nobody can repackage it as a closed, paid product.
- We can learn from and, where needed, reuse GPL reference implementations.
- All permissive and LGPL dependencies remain compatible.
- The licence text is added when the GitHub repository is created.
