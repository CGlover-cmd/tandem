"""Mute and unmute Windows' default sound output, through Core Audio's endpoint volume (ADR-0020).

Used only while the PC's audio is captured with process loopback, which records the apps
before the output's mute (Spike G). With classic loopback a mute would silence AirPlay too, so
`available` says no and nothing is muted.

Every call opens its own COM objects and releases them, so it works from any thread. Endpoint
ids are the PC's own device ids: never logged.
"""

from __future__ import annotations

import ctypes
import uuid
from collections.abc import Callable
from typing import Any


class _GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]


def _guid(text: str) -> _GUID:  # pragma: no cover - needs Windows audio
    value = _GUID()
    ctypes.memmove(value.data, uuid.UUID(text).bytes_le, 16)
    return value


CLSID_ENUMERATOR = _guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_ENUMERATOR = _guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
IID_ENDPOINT_VOLUME = _guid("5CDF2C82-841E-4546-9722-0CF74078229A")
_CLSCTX_ALL = 23
_RENDER, _CONSOLE = 0, 0
_RPC_E_CHANGED_MODE = -2147417850


def _method(
    obj: ctypes.c_void_p, index: int, *argtypes: Any
) -> Callable[..., Any]:  # pragma: no cover - needs Windows audio
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    function = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)(vtable[index])
    return lambda *args: function(obj, *args)


def _release(obj: ctypes.c_void_p) -> None:  # pragma: no cover - needs Windows audio
    if obj:
        vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])(obj)


class WindowsSpeakerMute:  # pragma: no cover - needs Windows audio
    """A `SpeakerMute` for Windows' default output. `allowed` is asked before muting: it is
    False once the capture had to fall back to classic loopback."""

    def __init__(self, allowed: Callable[[], bool]) -> None:
        self._allowed = allowed

    def available(self) -> bool:
        return self._allowed()

    def default_output(self) -> str | None:
        with _Com() as com:
            device = com.default_device()
            if not device:
                return None  # no sound output at all
            try:
                text = ctypes.c_void_p()
                _method(device, 5, ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(text))  # GetId
                try:
                    return ctypes.wstring_at(text.value) if text.value else None
                finally:
                    _free(text)
            finally:
                _release(device)

    def muted(self, endpoint: str) -> bool:
        with _Com() as com:
            volume = com.volume(endpoint)
            try:
                value = ctypes.c_int()
                _method(volume, 15, ctypes.POINTER(ctypes.c_int))(ctypes.byref(value))  # GetMute
                return bool(value.value)
            finally:
                _release(volume)

    def set_muted(self, endpoint: str, on: bool) -> None:
        with _Com() as com:
            volume = com.volume(endpoint)
            try:
                _method(volume, 14, ctypes.c_int, ctypes.c_void_p)(int(on), None)  # SetMute
            finally:
                _release(volume)


def _uninitialize() -> None:  # pragma: no cover - needs Windows audio
    uninitialize = ctypes.WinDLL("ole32").CoUninitialize
    uninitialize.restype = None  # returns nothing: OleDLL would read garbage as an error
    uninitialize()


def _free(memory: ctypes.c_void_p) -> None:  # pragma: no cover - needs Windows audio
    if memory:
        free = ctypes.WinDLL("ole32").CoTaskMemFree
        free.restype = None
        free.argtypes = [ctypes.c_void_p]
        free(memory)


class _Com:  # pragma: no cover - needs Windows audio
    """An MMDeviceEnumerator for one call, on whatever thread this is."""

    def __enter__(self) -> _Com:
        ole32 = ctypes.OleDLL("ole32")  # raises OSError for a failed HRESULT
        self._uninitialize = True
        try:
            ole32.CoInitializeEx(None, 0)  # multithreaded apartment
        except OSError as exc:  # this thread already chose another apartment: fine
            if exc.winerror != _RPC_E_CHANGED_MODE:
                raise
            self._uninitialize = False
        self._enumerator = ctypes.c_void_p()
        try:
            ole32.CoCreateInstance(
                ctypes.byref(CLSID_ENUMERATOR),
                None,
                _CLSCTX_ALL,
                ctypes.byref(IID_ENUMERATOR),
                ctypes.byref(self._enumerator),
            )
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_exc: object) -> None:
        _release(self._enumerator)
        if self._uninitialize:
            _uninitialize()

    def default_device(self) -> ctypes.c_void_p:
        device = ctypes.c_void_p()
        get_default = _method(
            self._enumerator, 4, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)
        )
        try:
            get_default(_RENDER, _CONSOLE, ctypes.byref(device))
        except OSError:
            return ctypes.c_void_p()  # E_NOTFOUND: no sound output
        return device

    def volume(self, endpoint: str) -> ctypes.c_void_p:
        device = ctypes.c_void_p()
        _method(self._enumerator, 5, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p))(
            endpoint, ctypes.byref(device)
        )  # GetDevice
        try:
            volume = ctypes.c_void_p()
            _method(
                device,
                3,
                ctypes.POINTER(_GUID),
                ctypes.c_uint,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            )(ctypes.byref(IID_ENDPOINT_VOLUME), _CLSCTX_ALL, None, ctypes.byref(volume))
            return volume
        finally:
            _release(device)
