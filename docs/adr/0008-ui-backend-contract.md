# ADR-0008: The UI defines the backend contract it needs

- Status: Accepted; the QML, `Theme` and PySide6 parts are replaced by
  [ADR-0010](0010-heroui-web-front-end.md). The `Backend` contract and `DemoBackend` stand.
- Date: 2026-10-20

## Context
The UI shell (Phase 2) is being built alongside the core engine (Phase 1). ADR-0002 says the UI
talks to the engine only through a service API, but that API didn't exist yet, and the UI should
not wait for it or import engine modules directly.

## Decision
- The UI declares what it needs as a small `Backend` protocol in `tandem.ui.backend`: device
  snapshots, change events, connect, disconnect and PIN pairing. Its enums mirror the engine's
  `DeviceKind` and `ConnectionState` values, so the engine side is a straight mapping.
- The engine provides an adapter that implements `Backend`. Until it exists, `DemoBackend` (invented
  devices, no network) runs the UI and its tests.
- ViewModels (pure Python, `tandem.ui.viewmodels`) hold all UI state; QML only binds to them.
- Design tokens (colour, type, spacing, motion) live in one QML singleton, `Theme`, and a test
  checks every text colour against WCAG AA in light and dark mode.
- The UI depends on `PySide6-Essentials` (not the full `PySide6`, which adds large unused modules)
  and `qasync`, installed as an optional `ui` dependency group.

## Consequences
- UI and engine work can proceed in parallel; the contract is the only meeting point.
- The demo backend doubles as a test fixture and a way for contributors to try the UI without
  devices.
- When the engine adapter lands, any mismatch shows up in one place: the adapter. It landed as
  `tandem.bridge.EngineBackend`; the contract gained `Appearance` (ADR-0010) and pairing flows
  with more than one PIN (`PairingFlow.steps`), because an Apple TV pairs remote control and
  AirPlay separately. Phase 3 added `ControlsSnapshot` and `ControlsChanged`, and the remote,
  media, volume and power commands (mirroring the engine's control API, ADR-0009).
  Phase 9a added typed commands: `preview_command` and `run_command`, returning a
  `CommandOutcome` (ADR-0011).
