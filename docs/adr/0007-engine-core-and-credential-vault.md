# ADR-0007: Engine core structure and the encrypted credential vault

- Status: Accepted
- Date: 2026-10-21

## Context
Phase 1 builds the engine core: discovery, a device registry, connection handling, settings,
logging and pairing credentials. Spike A kept pyatv's pairing keys in a plain JSON file in
`local/`, which is fine for a spike but not for users. The engine also has to stay testable
without real devices, and nothing it logs may reveal device names or addresses (ADR-0004).

## Decision
- **Package layout:** `src/tandem/engine/` holds protocol-agnostic core modules (event bus,
  registry, discovery loop, connection session, settings, logs, vault). Only
  `engine/adapters/` imports pyatv; the core takes small callables (a scanner, a connector),
  so tests use fakes and the UI never sees pyatv types.
- **Events:** a synchronous, in-process event bus of frozen dataclasses, run on the asyncio
  loop thread. The UI subscribes to it through its ViewModels.
- **Connections:** one state machine per device (disconnected, connecting, connected, waiting,
  failed) with exponential backoff and jitter. Events carry an error's type name, never its
  message, because messages can contain addresses.
- **Credentials:** a pyatv storage backend (`CredentialVault`) that writes pyatv's storage model
  as JSON encrypted with the Windows Data Protection API (DPAPI), bound to the signed-in user.
  pyatv then saves and loads credentials itself during pair and connect. A vault that can't be
  read raises an error and is never overwritten.
- **Files:** everything lives in `%LOCALAPPDATA%\Tandem` (settings JSON, `credentials.bin`,
  `logs/`); the `TANDEM_HOME` variable overrides it.
- **Logging:** JSON-lines files, rotated by size. Every line, file or console, passes through
  a redactor that swaps known device names and ids, IP and MAC addresses, UUIDs, emails and
  user-folder paths for stable placeholders such as `<device-1>`.

## Consequences
- DPAPI needs no key management and no extra package, but credentials don't move to another PC
  or Windows account: the user pairs again there. That matches pyatv's own advice to keep
  pairing keys per machine.
- The vault depends on pyatv's storage model. pyatv is pinned to a minor version; moving the pin
  means checking the vault round-trip test still passes.
- Logs are safe to attach to a public issue by default, at the cost of not showing real names
  while debugging. The developer tool has `--show-private` for the maintainer's own terminal.
