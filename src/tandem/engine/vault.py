"""Encrypted JSON files for secrets (ADR-0007).

`EncryptedJsonFile` stores one JSON object: a short header, then the JSON encrypted with DPAPI
for the current Windows user. The pyatv credential store in `adapters` is built on it.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol

from tandem.engine import dpapi

_MAGIC = b"TANDEM-VAULT-1\n"
# Fixed, public entropy: it only separates our blobs from other apps' DPAPI data.
_ENTROPY = b"tandem.credential-vault.v1"


class Protector(Protocol):
    def protect(self, data: bytes) -> bytes: ...
    def unprotect(self, data: bytes) -> bytes: ...


class DpapiProtector:
    def protect(self, data: bytes) -> bytes:
        return dpapi.protect(data, _ENTROPY)

    def unprotect(self, data: bytes) -> bytes:
        return dpapi.unprotect(data, _ENTROPY)


class VaultError(Exception):
    """The vault file exists but can't be read. It is left as is; nothing is overwritten."""


class EncryptedJsonFile:
    def __init__(self, path: Path, protector: Protector | None = None) -> None:
        self.path = path
        self._protector = protector or DpapiProtector()

    def read(self) -> dict[str, Any] | None:
        """Decrypt and parse the file; None if it doesn't exist. Raises VaultError."""
        try:
            blob = self.path.read_bytes()
        except FileNotFoundError:
            return None
        if not blob.startswith(_MAGIC):
            raise VaultError("not a Tandem credential vault")
        try:
            data = json.loads(self._protector.unprotect(blob[len(_MAGIC) :]).decode("utf-8"))
        except (OSError, ValueError) as exc:
            # OSError covers DPAPI refusing (another user or PC); ValueError bad JSON/UTF-8.
            raise VaultError(f"can't decrypt the credential vault ({type(exc).__name__})") from exc
        if not isinstance(data, dict):
            raise VaultError("credential vault has the wrong shape")
        return data  # pyright: ignore[reportUnknownVariableType]

    def write(self, data: dict[str, Any]) -> None:
        """Encrypt and write atomically, so a crash mid-write never loses the old file."""
        blob = _MAGIC + self._protector.protect(json.dumps(data).encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".credentials-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(blob)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
