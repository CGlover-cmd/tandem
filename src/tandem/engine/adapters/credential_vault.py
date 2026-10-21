"""pyatv storage backed by the encrypted vault file (ADR-0007).

pyatv reads and writes pairing credentials through this storage during scan, pair and connect,
so they are only ever on disk encrypted with DPAPI.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pyatv.exceptions import SettingsError
from pyatv.storage import AbstractStorage, StorageModel
from pydantic import ValidationError

from tandem.engine.vault import EncryptedJsonFile, Protector, VaultError


class CredentialVault(AbstractStorage):
    def __init__(self, path: Path, protector: Protector | None = None) -> None:
        super().__init__()
        self._file = EncryptedJsonFile(path, protector)
        self._loaded = False

    async def load(self) -> None:
        """Read and decrypt the vault. A missing file is an empty vault."""
        raw = await asyncio.to_thread(self._file.read)
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
        if not self._loaded and self._file.path.exists():
            # Saving before loading would replace stored credentials with an empty set.
            raise VaultError("load() the vault before saving it")
        dumped = dict(self)
        if self.has_changed(dumped):
            await asyncio.to_thread(self._file.write, dumped)
            self.update_hash(dumped)

    def __str__(self) -> str:
        return "CredentialVault"
