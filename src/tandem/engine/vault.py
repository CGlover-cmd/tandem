"""Encrypted credential vault (ADR-0007).

The vault is a pyatv storage backend, so pyatv reads and writes pairing credentials through it
directly during scan, pair and connect. On disk it is a small header followed by the pyatv
storage model as JSON, encrypted with DPAPI for the current Windows user.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol

from pyatv.exceptions import SettingsError
from pyatv.storage import AbstractStorage, StorageModel
from pydantic import ValidationError

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


class CredentialVault(AbstractStorage):
    def __init__(self, path: Path, protector: Protector | None = None) -> None:
        super().__init__()
        self._path = path
        self._protector = protector or DpapiProtector()
        self._loaded = False

    async def load(self) -> None:
        """Read and decrypt the vault. A missing file is an empty vault."""
        raw = await asyncio.to_thread(self._read)
        if raw is not None:
            try:
                self.storage_model = StorageModel.model_validate(raw)
            except (ValidationError, SettingsError) as exc:
                raise VaultError("credential vault contents are not valid") from exc
            # Hash what was read, not the re-serialised model, so changes made by validation
            # are still saved (the same approach as pyatv's FileStorage).
            self.update_hash(raw)
        else:
            self.update_hash(dict(self))  # an empty vault needs no file until it changes
        self._loaded = True

    async def save(self) -> None:
        """Encrypt and write the vault if anything changed."""
        if not self._loaded and self._path.exists():
            # Saving before loading would replace stored credentials with an empty set.
            raise VaultError("load() the vault before saving it")
        dumped = dict(self)
        if self.has_changed(dumped):
            await asyncio.to_thread(self._write, dumped)
            self.update_hash(dumped)

    def _read(self) -> dict[str, Any] | None:
        try:
            blob = self._path.read_bytes()
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

    def _write(self, dumped: dict[str, Any]) -> None:
        blob = _MAGIC + self._protector.protect(json.dumps(dumped).encode("utf-8"))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".credentials-", dir=self._path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(blob)
            os.replace(tmp, self._path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def __str__(self) -> str:
        return "CredentialVault"
