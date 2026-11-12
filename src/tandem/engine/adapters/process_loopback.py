"""Capture what every app plays except Tandem, before the speakers' volume and mute (ADR-0020).

Classic WASAPI loopback (`adapters/loopback.py`) records the default output after Windows
applies its volume and mute, so muting the PC's speakers silences AirPlay too (Spike C).
Process loopback (Windows 10 2004+) records the apps' own streams instead: here every
process except Tandem's own tree, so Tandem can mute the speakers, and can play to them
itself without hearing its own sound come back (Spike G).

miniaudio has a switch for this, but the build pyatv pins opens it the wrong way on desktop
Windows, so this talks to Core Audio directly through ctypes: `ActivateAudioInterfaceAsync`
on the process-loopback virtual device, then an event-driven shared-mode capture client that
converts to 44.1 kHz, 16-bit stereo for AirPlay. One thread reads it; `on_pcm` gets the bytes.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import uuid
from collections.abc import Callable
from typing import Any

from tandem.engine.adapters.loopback import LoopbackCapture
from tandem.engine.audio import CHANNELS, SAMPLE_RATE, AudioError

_LOGGER = logging.getLogger(__name__)

_BUFFER_HNS = 2_000_000  # 200 ms of buffer on Windows' side, in 100 ns units
_WAIT_MS = 100
_MIN_BUILD = 19041  # Windows 10 2004


def supported() -> bool:
    """Process loopback exists on this Windows (10 2004 or later)."""
    if sys.platform != "win32":
        return False
    return sys.getwindowsversion().build >= _MIN_BUILD


class CaptureMode:
    """Which capture the PC's audio uses. `process` turns False for good once process loopback
    fails to open, so Tandem stops muting the speakers (that would silence AirPlay too)."""

    def __init__(self, process: bool | None = None) -> None:
        self.process = supported() if process is None else process


class SystemCapture:
    """A `PcmCapture` of the PC's audio: process loopback where it works, classic otherwise."""

    def __init__(self, mode: CaptureMode) -> None:
        self._mode = mode
        self._capture: ProcessLoopbackCapture | LoopbackCapture | None = None

    def start(self, on_pcm: Callable[[bytes], None]) -> None:
        if self._capture is not None:
            return
        if self._mode.process:
            capture = ProcessLoopbackCapture()
            try:
                capture.start(on_pcm)
            except AudioError as exc:
                _LOGGER.warning("App audio capture didn't open; using the classic one (%s)", exc)
                self._mode.process = False
            else:
                self._capture = capture
                return
        classic = LoopbackCapture()
        classic.start(on_pcm)
        self._capture = classic

    def stop(self) -> None:
        capture, self._capture = self._capture, None
        if capture is not None:
            capture.stop()


class ProcessLoopbackCapture:  # pragma: no cover - needs Windows audio
    """A `PcmCapture` of every app but Tandem. Same shape as `LoopbackCapture`."""

    def __init__(self, exclude_pid: int | None = None) -> None:
        self._exclude_pid = os.getpid() if exclude_pid is None else exclude_pid
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._started = threading.Event()
        self._error: BaseException | None = None

    def start(self, on_pcm: Callable[[bytes], None]) -> None:
        if self._thread is not None:
            return
        if not supported():
            raise AudioError("process audio capture needs Windows 10 2004 or later")
        self._stop.clear()
        self._started.clear()
        self._error = None
        thread = threading.Thread(
            target=self._run, args=(on_pcm,), name="tandem-process-loopback", daemon=True
        )
        thread.start()
        self._started.wait(5)
        if self._error is not None or not self._started.is_set():
            self._stop.set()
            thread.join(2)
            error = self._error
            raise AudioError(
                f"can't capture app audio ({type(error).__name__ if error else 'timeout'})"
            )
        self._thread = thread

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is not None:
            self._stop.set()
            thread.join(2)

    def _run(self, on_pcm: Callable[[bytes], None]) -> None:
        try:
            _capture(self._exclude_pid, on_pcm, self._started, self._stop)
        except BaseException as exc:  # reported to start(), or logged once it's running
            self._error = exc
            if self._started.is_set():
                _LOGGER.warning("App audio capture stopped (%s)", type(exc).__name__)
            self._started.set()


# ---- Core Audio through COM vtables -----------------------------------------------------


class _GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]


def _guid(text: str) -> _GUID:  # pragma: no cover - needs Windows audio
    value = _GUID()
    ctypes.memmove(value.data, uuid.UUID(text).bytes_le, 16)
    return value


def _same(a: Any, b: _GUID) -> bool:  # pragma: no cover - needs Windows audio
    return bytes(a.contents.data) == bytes(b.data)


IID_IUNKNOWN = _guid("00000000-0000-0000-C000-000000000046")
IID_IAGILE_OBJECT = _guid("94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90")
IID_COMPLETION_HANDLER = _guid("41D949AB-9862-444A-80F6-C261334DA5EB")
IID_IAUDIO_CLIENT = _guid("1CB9AD4C-DBFA-4C32-B178-C2F568A703B2")
IID_IAUDIO_CAPTURE_CLIENT = _guid("C8ADBD64-E71E-48A0-A4DE-185C395CD317")

_VIRTUAL_DEVICE = "VAD\\Process_Loopback"
_VT_BLOB = 65
_ACTIVATION_PROCESS_LOOPBACK = 1
_EXCLUDE_TARGET_TREE = 1
_SHARED = 0
_FLAGS = 0x00020000 | 0x00040000 | 0x80000000 | 0x08000000
"""LOOPBACK | EVENTCALLBACK | AUTOCONVERTPCM | SRC_DEFAULT_QUALITY."""
_SILENT = 0x2


class _ActivationParams(ctypes.Structure):
    _fields_ = [
        ("activation_type", ctypes.c_int),
        ("target_process_id", ctypes.c_uint32),
        ("loopback_mode", ctypes.c_int),
    ]


class _Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.c_void_p)]


class _PropVariant(ctypes.Structure):
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("reserved1", ctypes.c_ushort),
        ("reserved2", ctypes.c_ushort),
        ("reserved3", ctypes.c_ushort),
        ("blob", _Blob),
    ]


class _WaveFormat(ctypes.Structure):
    _fields_ = [
        ("format_tag", ctypes.c_ushort),
        ("channels", ctypes.c_ushort),
        ("samples_per_sec", ctypes.c_uint32),
        ("avg_bytes_per_sec", ctypes.c_uint32),
        ("block_align", ctypes.c_ushort),
        ("bits_per_sample", ctypes.c_ushort),
        ("size", ctypes.c_ushort),
    ]


def _method(
    obj: ctypes.c_void_p, index: int, *argtypes: Any
) -> Callable[..., Any]:  # pragma: no cover - needs Windows audio
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)
    function = prototype(vtable[index])
    return lambda *args: function(obj, *args)


def _release(obj: ctypes.c_void_p) -> None:  # pragma: no cover - needs Windows audio
    if obj:
        vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])(obj)


class _CompletionHandler:  # pragma: no cover - needs Windows audio
    """A minimal free-threaded COM object for `ActivateAudioInterfaceAsync` to call back."""

    def __init__(self) -> None:
        self.done = threading.Event()
        hresult, void_p = ctypes.HRESULT, ctypes.c_void_p
        query = ctypes.WINFUNCTYPE(hresult, void_p, ctypes.POINTER(_GUID), ctypes.POINTER(void_p))
        count = ctypes.WINFUNCTYPE(ctypes.c_ulong, void_p)
        completed = ctypes.WINFUNCTYPE(hresult, void_p, void_p)
        self._functions = (
            query(self._query),
            count(self._count),
            count(self._count),
            completed(self._completed),
        )
        self._vtable = (void_p * 4)(*(ctypes.cast(f, void_p) for f in self._functions))
        self._object = ctypes.pointer(ctypes.pointer(self._vtable))

    @property
    def pointer(self) -> ctypes.c_void_p:
        return ctypes.cast(self._object, ctypes.c_void_p)

    def _query(self, this: int, iid: Any, out: Any) -> int:
        if any(
            _same(iid, known) for known in (IID_IUNKNOWN, IID_IAGILE_OBJECT, IID_COMPLETION_HANDLER)
        ):
            out[0] = this
            return 0
        out[0] = None
        return -2147467262  # E_NOINTERFACE

    @staticmethod
    def _count(_this: int) -> int:
        return 1  # a static object: reference counts don't matter

    def _completed(self, _this: int, _operation: int) -> int:
        self.done.set()
        return 0


def _activate(exclude_pid: int) -> ctypes.c_void_p:  # pragma: no cover - needs Windows audio
    """An IAudioClient on the process-loopback device that leaves out `exclude_pid`'s tree."""
    mmdevapi = ctypes.WinDLL("mmdevapi")
    activate = mmdevapi.ActivateAudioInterfaceAsync
    activate.restype = ctypes.HRESULT
    activate.argtypes = [
        ctypes.c_wchar_p,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(_PropVariant),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    params = _ActivationParams(_ACTIVATION_PROCESS_LOOPBACK, exclude_pid, _EXCLUDE_TARGET_TREE)
    variant = _PropVariant(vt=_VT_BLOB)
    variant.blob = _Blob(
        ctypes.sizeof(params), ctypes.cast(ctypes.pointer(params), ctypes.c_void_p)
    )
    handler = _CompletionHandler()
    operation = ctypes.c_void_p()
    activate(
        _VIRTUAL_DEVICE,
        ctypes.byref(IID_IAUDIO_CLIENT),
        ctypes.byref(variant),
        handler.pointer,
        ctypes.byref(operation),
    )
    try:
        if not handler.done.wait(5):
            raise AudioError("process loopback didn't activate")
        client = ctypes.c_void_p()
        get_result = _method(
            operation, 3, ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_void_p)
        )
        status = ctypes.c_long()
        get_result(ctypes.byref(status), ctypes.byref(client))
        if status.value < 0 or not client:
            raise OSError(status.value, "process loopback activation failed")
        return client
    finally:
        _release(operation)


def _capture(  # pragma: no cover - needs Windows audio
    exclude_pid: int,
    on_pcm: Callable[[bytes], None],
    started: threading.Event,
    stop: threading.Event,
) -> None:
    ole32 = ctypes.OleDLL("ole32")
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.CreateEventW.restype = ctypes.c_void_p
    kernel32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    ole32.CoInitializeEx(None, 0)  # multithreaded apartment on this thread
    client, capture = ctypes.c_void_p(), ctypes.c_void_p()
    event = None
    try:
        client = _activate(exclude_pid)
        block = CHANNELS * 2
        wave = _WaveFormat(1, CHANNELS, SAMPLE_RATE, SAMPLE_RATE * block, block, 16, 0)
        initialize = _method(
            client,
            3,
            ctypes.c_int,
            ctypes.c_uint32,
            ctypes.c_longlong,
            ctypes.c_longlong,
            ctypes.POINTER(_WaveFormat),
            ctypes.c_void_p,
        )
        initialize(_SHARED, _FLAGS, _BUFFER_HNS, 0, ctypes.byref(wave), None)
        event = kernel32.CreateEventW(None, 0, 0, None)
        _method(client, 13, ctypes.c_void_p)(event)  # SetEventHandle
        _method(client, 14, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))(
            ctypes.byref(IID_IAUDIO_CAPTURE_CLIENT), ctypes.byref(capture)
        )
        get_buffer = _method(
            capture,
            3,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        release_buffer = _method(capture, 4, ctypes.c_uint32)
        next_size = _method(capture, 5, ctypes.POINTER(ctypes.c_uint32))
        _method(client, 10)()  # Start
        started.set()
        data, frames, flags, waiting = (
            ctypes.c_void_p(),
            ctypes.c_uint32(),
            ctypes.c_uint32(),
            ctypes.c_uint32(),
        )
        while not stop.is_set():
            kernel32.WaitForSingleObject(event, _WAIT_MS)
            next_size(ctypes.byref(waiting))
            while waiting.value and not stop.is_set():
                get_buffer(
                    ctypes.byref(data), ctypes.byref(frames), ctypes.byref(flags), None, None
                )
                size = frames.value * block
                if flags.value & _SILENT or not data:
                    chunk = bytes(size)
                else:
                    chunk = ctypes.string_at(data, size)
                release_buffer(frames.value)
                if chunk:
                    on_pcm(chunk)
                next_size(ctypes.byref(waiting))
        _method(client, 11)()  # Stop
    finally:
        _release(capture)
        _release(client)
        if event:
            kernel32.CloseHandle(event)
        uninitialize = ctypes.WinDLL("ole32").CoUninitialize
        uninitialize.restype = None  # returns nothing: OleDLL would read garbage as an error
        uninitialize()
