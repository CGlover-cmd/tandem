from __future__ import annotations

import sys
from ipaddress import IPv4Address
from pathlib import Path

import pytest
from pyatv import conf
from pyatv.const import Protocol

from tandem.engine import dpapi
from tandem.engine.adapters.credential_vault import CredentialVault
from tandem.engine.vault import VaultError

FAKE_CREDENTIALS = "invented-pairing-blob-0001"
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")


class ReversingProtector:
    """Stand-in for DPAPI: reverses bytes, so plaintext never appears in the file."""

    def protect(self, data: bytes) -> bytes:
        return data[::-1]

    def unprotect(self, data: bytes) -> bytes:
        return data[::-1]


class RefusingProtector(ReversingProtector):
    def unprotect(self, data: bytes) -> bytes:
        raise OSError("refused")


def _config() -> conf.AppleTV:
    config = conf.AppleTV(IPv4Address("192.0.2.20"), "Den TV")
    config.add_service(conf.ManualService("id-companion-1", Protocol.Companion, 49152, {}))
    return config


async def _store_credentials(vault: CredentialVault) -> None:
    await vault.load()
    settings = await vault.get_settings(_config())
    settings.protocols.companion.credentials = FAKE_CREDENTIALS
    await vault.save()


async def _read_credentials(vault: CredentialVault) -> str | None:
    await vault.load()
    return (await vault.get_settings(_config())).protocols.companion.credentials


async def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "credentials.bin"
    await _store_credentials(CredentialVault(path, ReversingProtector()))
    assert FAKE_CREDENTIALS.encode() not in path.read_bytes()
    assert await _read_credentials(CredentialVault(path, ReversingProtector())) == FAKE_CREDENTIALS


async def test_missing_file_is_an_empty_vault(tmp_path: Path) -> None:
    vault = CredentialVault(tmp_path / "credentials.bin", ReversingProtector())
    await vault.load()
    assert vault.settings == []
    await vault.save()  # nothing changed: nothing written
    assert not (tmp_path / "credentials.bin").exists()


async def test_save_before_load_refuses_to_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "credentials.bin"
    await _store_credentials(CredentialVault(path, ReversingProtector()))
    before = path.read_bytes()
    with pytest.raises(VaultError, match="load"):
        await CredentialVault(path, ReversingProtector()).save()
    assert path.read_bytes() == before


async def test_foreign_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "credentials.bin"
    path.write_bytes(b"something else")
    with pytest.raises(VaultError, match="not a Tandem"):
        await CredentialVault(path, ReversingProtector()).load()


async def test_undecryptable_vault_is_rejected_and_kept(tmp_path: Path) -> None:
    path = tmp_path / "credentials.bin"
    await _store_credentials(CredentialVault(path, ReversingProtector()))
    before = path.read_bytes()
    vault = CredentialVault(path, RefusingProtector())
    with pytest.raises(VaultError, match="decrypt"):
        await vault.load()
    with pytest.raises(VaultError):
        await vault.save()
    assert path.read_bytes() == before


@pytest.mark.parametrize("payload", [b"[]", b'{"version": 99, "devices": []}', b"\xff"])
async def test_invalid_contents_are_rejected(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "credentials.bin"
    path.write_bytes(b"TANDEM-VAULT-1\n" + payload[::-1])
    vault = CredentialVault(path, ReversingProtector())
    with pytest.raises(VaultError):
        await vault.load()
    with pytest.raises(VaultError):
        await vault.save()


def test_str_hides_the_path(tmp_path: Path) -> None:
    assert str(CredentialVault(tmp_path / "credentials.bin")) == "CredentialVault"


@windows_only
async def test_round_trip_with_dpapi(tmp_path: Path) -> None:
    path = tmp_path / "credentials.bin"
    await _store_credentials(CredentialVault(path))
    assert FAKE_CREDENTIALS.encode() not in path.read_bytes()
    assert await _read_credentials(CredentialVault(path)) == FAKE_CREDENTIALS


@windows_only
def test_dpapi_round_trip_and_entropy() -> None:
    blob = dpapi.protect(b"hello", b"entropy-a")
    assert b"hello" not in blob
    assert dpapi.unprotect(blob, b"entropy-a") == b"hello"
    with pytest.raises(dpapi.DpapiError):
        dpapi.unprotect(blob, b"entropy-b")
    assert dpapi.unprotect(dpapi.protect(b"")) == b""


def test_dpapi_needs_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(dpapi.DpapiError, match="Windows"):
        dpapi.protect(b"x")
