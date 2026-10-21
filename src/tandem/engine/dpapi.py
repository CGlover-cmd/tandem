"""Windows Data Protection API (DPAPI) through ctypes.

DPAPI encrypts data with a key tied to the signed-in Windows user, so the credential file is
useless if copied to another account or PC. No key management of our own, no extra packages.
"""

from __future__ import annotations

import ctypes
import sys
from typing import Any

_CRYPTPROTECT_UI_FORBIDDEN = 0x01
_DESCRIPTION = "Tandem credentials"


class DpapiError(OSError):
    """DPAPI is unavailable, or refused to encrypt or decrypt."""


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_Blob, Any]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _api() -> tuple[Any, Any]:
    if sys.platform != "win32":
        raise DpapiError("DPAPI is only available on Windows")
    crypt32: Any = ctypes.WinDLL("crypt32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32: Any = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    return crypt32, kernel32


def _take(kernel32: Any, blob: _Blob) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        kernel32.LocalFree(blob.pbData)


def protect(data: bytes, entropy: bytes = b"") -> bytes:
    """Encrypt `data` for the current Windows user."""
    crypt32, kernel32 = _api()
    data_in, _keep_in = _blob(data)
    entropy_blob, _keep_entropy = _blob(entropy)
    data_out = _Blob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(data_in),
        ctypes.c_wchar_p(_DESCRIPTION),
        ctypes.byref(entropy_blob) if entropy else None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(data_out),
    )
    if not ok:
        raise DpapiError(ctypes.get_last_error(), "CryptProtectData failed")  # type: ignore[attr-defined]
    return _take(kernel32, data_out)


def unprotect(data: bytes, entropy: bytes = b"") -> bytes:
    """Decrypt data from `protect`. Fails for another user, PC, or the wrong entropy."""
    crypt32, kernel32 = _api()
    data_in, _keep_in = _blob(data)
    entropy_blob, _keep_entropy = _blob(entropy)
    data_out = _Blob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(data_in),
        None,
        ctypes.byref(entropy_blob) if entropy else None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(data_out),
    )
    if not ok:
        raise DpapiError(ctypes.get_last_error(), "CryptUnprotectData failed")  # type: ignore[attr-defined]
    return _take(kernel32, data_out)
