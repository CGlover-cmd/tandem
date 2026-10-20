# Privacy guardrails for contributors

This repository is public. It must never reveal anything about the people who build or test it,
their homes or their networks. These rules apply to code, docs, tests, fixtures, screenshots,
issues and commit metadata.

## Never commit

- Real names, email addresses, usernames or home-folder paths (e.g. `C:\Users\<name>\...`)
- Device names as set in the Home app (they often contain names or room names)
- IP addresses, MAC addresses, device identifiers, serial numbers, Wi-Fi network names
- Pairing credentials, keys, tokens, or anything from a credential store
- Raw discovery dumps, packet captures (`.pcap`/`.pcapng`) or logs from a real network
- Screenshots or recordings showing real device names, notifications, files or desktops

## Where private data goes instead

`local/` is git-ignored. Discovery scans, captures, logs, credentials and the personal deny-list
(`local/denylist.txt`, one term per line) live there and never leave the machine.

## Automated checks

`pre-commit` runs before every commit:

- **detect-secrets** looks for secrets and keys.
- **tools/check_private_info.py** blocks private IPs, MAC addresses, email addresses (except
  GitHub `noreply` addresses), user-folder paths, and every term in `local/denylist.txt`.

A blocked commit is a feature, not a nuisance: fix the content; don't bypass the hook.

## Test data

Fixtures use invented values: names like `Living Room Speaker`, documentation IP ranges
(`192.0.2.0/24`, RFC 5737) and made-up identifiers like `AA:BB:CC:00:00:01`.

## Git identity

Commits use the GitHub `noreply` email. On GitHub, under Settings → Emails, enable
**Keep my email addresses private** and **Block command line pushes that expose my email**.

## App behaviour

The app collects no telemetry. Crash reports are opt-in, and diagnostics bundles are redacted
(names, addresses and identifiers replaced with stable placeholders) before they are written.
