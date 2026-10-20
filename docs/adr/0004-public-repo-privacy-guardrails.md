# ADR-0004: Public repository with privacy guardrails

- Status: Accepted
- Date: 2026-10-20

## Context
Development happens in a public GitHub repository from day one. Building and testing a
home-network app naturally produces private data: device names, addresses, identifiers,
pairing keys, logs and packet captures. Commit metadata can also reveal a personal email.

## Decision
- All private data lives in the git-ignored `local/` folder.
- Pre-commit hooks (detect-secrets plus `tools/check_private_info.py`) block secrets, private IPs,
  MAC addresses, emails, user-folder paths and every term in a personal deny-list.
- Commits use the GitHub `noreply` email; GitHub's email-privacy push protection is enabled.
- Test fixtures and screenshots use invented data only.
- The app itself has no telemetry and redacts diagnostics bundles.

The full rules are in [PRIVACY.md](../PRIVACY.md).

## Consequences
Occasional false positives from the hook; the fix is to change the content, never to bypass it.
