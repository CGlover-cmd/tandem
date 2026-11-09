# ADR-0019: One bridge; the demo runs on the engine

- Status: Accepted
- Date: 2026-11-08

## Context
An architecture review (after 1.2.0) found most of the cost of a new feature in the layer
between the engine and the window. `DemoBackend` (ADR-0008) had grown into a second copy of the
bridge: its own pairing flow, retries, controls, outputs and typed-command services, about 800
lines that every feature had to repeat, and the demo window (used for every screenshot) never ran
the real bridge. Output behaviour (saved volume and delay, failures, groups, line-up) lived in
the bridge, so the command bar called back into it. Engine errors were worded three times, and
the bridge sent English sentences, against the rule that Python sends codes.

## Decision
- **The demo is a device adapter.** `tandem.engine.adapters.demo.DemoDevices` implements the
  engine's `Backend` with invented devices, next to pyatv. `tandem.bridge.DemoBackend` is
  `EngineBackend` over it. The window's `Backend` protocol (ADR-0008) stays as the contract; it
  has one implementation. The window's tests run on the demo (`tests/ui/demo_harness.py`).
- **Outputs live in the engine.** `tandem.engine.outputs.Outputs` (`engine.outputs`) owns saved
  settings, starting and failed states, recent outputs, groups, "turn my speakers back on" and
  line-up, and announces `OutputsChanged`. Every caller switches outputs there.
- **Intents in the engine.** `DeviceControls.play()`, `pause()` and `play_pause()` pick the
  command the app offers; `control.failure_of()` classifies control errors once.
- **Problem codes.** `BackendError.code` is a `tandem.ui.backend.Problem` value; the words are in
  `web/src/strings.ts` (`problems`).
- **A checked contract.** `tools/write_contract.py` writes `web/src/contract.generated.ts` (a demo
  snapshot typed as `AppState`, every command name, every problem code); the web type check and
  tests fail when Python and `types.ts` drift apart. Window commands are registered per panel in
  a `CommandTable` (`tandem.ui.window_commands`).

## Consequences
- A feature is written once, in the engine or the bridge; the demo gets it for free.
- Demo screenshots and window tests exercise the real pairing, connection, control, output and
  command code. The demo needs its adapter kept in step with what the window should show.
- Changing the snapshot or a command means running `python tools/write_contract.py`.
- Replaces the `DemoBackend` part of ADR-0008 and the demo half of ADR-0018's group code.
