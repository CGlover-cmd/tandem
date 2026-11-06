# ADR-0017: An installer around Python's embeddable runtime

- Status: Accepted
- Date: 2026-11-04

## Context
Phase 9 ships Tandem as a normal Windows install. Freezers (PyInstaller, Nuitka) produce our own
unsigned `.exe`, which SmartScreen warns about and Smart App Control blocks; the maintainer's PC
has Smart App Control on, so a frozen build can't even be tried there. Code signing (SignPath
Foundation) needs the maintainer to apply and isn't in place.

## Decision
- **App folder:** python.org's embeddable Python 3.11 (its `python.exe` and `pythonw.exe` are
  signed by the Python Software Foundation), with Tandem's wheel and its libraries installed into
  `python\Lib\site-packages` (`packaging/build_bundle.py`). zeroconf goes in as pure Python,
  since Smart App Control has blocked its compiled modules. Shortcuts run
  `pythonw.exe -m tandem.ui`.
- **Installer:** Inno Setup 6 (`packaging/tandem.iss`), per machine, Windows 10 22H2 or later.
  It adds one inbound firewall rule for that `pythonw.exe` on private networks (AirPlay timing,
  the Apple TV fetching a sent file, the Home app reaching the bridge), installs WebView2 with
  Microsoft's bootstrapper if it's missing, and offers desktop and sign-in shortcuts.
- **CI builds and tests it** (`.github/workflows/release.yml`) on every pull request: build the
  front end and wheel, build the app folder, smoke-test it (imports, then the app serving its
  window's page), build the installer, install it silently, smoke-test the installed copy,
  check the firewall rule, uninstall. A `v*` tag publishes a GitHub pre-release with the
  installer, a portable zip and the wheel.
- **One window per user:** a named mutex stops a second copy, which would knock the first off
  the Apple TV and clash on the Home bridge's port.

## Consequences
- The installer itself is still unsigned, so Smart App Control blocks it. Until signing is in
  place, the README gives a pip install path for those PCs.
- No auto-update yet: the README and release notes point at the releases page.
- The install is about 80 MB, mostly pythonnet, PIL, cryptography and the Python runtime.

## Addendum (1.1.0): pinned library versions
1.0.0's app folder was built with `pip install` and no version pins, so it picked up srptools
2.0, released after testing. Its new API broke pyatv's SRP handshake: every Apple TV pairing
failed as a "wrong PIN", and HomePods and AirPlay 2 speakers couldn't connect. The tests
missed it because they fake pyatv. Now:
- `packaging/constraints.txt` lists the exact tested version of every runtime library. The app
  folder, the release workflow and CI all install with `-c packaging/constraints.txt`, so CI
  tests what ships. `pyproject.toml` also caps srptools below 2 for pip installs.
- `tests/test_dependencies.py` runs pyatv's real SRP code against srptools' server side.
- Moving a pin is a deliberate change: update the file, run the tests, check on hardware.
