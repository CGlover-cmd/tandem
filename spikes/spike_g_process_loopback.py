"""Spike G: can Tandem keep the PC's speakers silent while it sends the PC's sound to AirPlay?

Today Tandem captures the default output with WASAPI loopback, which follows the Windows
volume and mute (Spike C): mute the speakers and AirPlay goes silent too. This spike checks
process loopback (Windows 10 2004+), which captures what every app plays except one process
tree, before the output's own volume is applied:

1. classic loopback, speakers muted            (expected: silent, the known problem)
2. process loopback, speakers muted            (hoped: hears the tone)
3. process loopback, the tone app's own session muted in the Volume Mixer
4. classic loopback, the tone app's session muted
5. process loopback, Windows system sounds session muted (a system beep from the child)

A child process plays a quiet tone (about -40 dBFS) so the run makes almost no sound, and the
speakers are muted during step 2 anyway. The mute and session states are put back afterwards.
Prints levels only: no device names or identifiers.

Run on Windows from the repo root: python spikes/spike_g_process_loopback.py
"""

from __future__ import annotations

import array
import ctypes
import math
import os
import subprocess
import sys
import threading
import time
import uuid
from ctypes import POINTER, byref, c_float, c_int, c_uint, c_void_p, wintypes
from typing import Any

RATE = 48_000
TONE_SECONDS = 3.0


# ---- the child: play a quiet tone -------------------------------------------------------


def play_tone(seconds: float, beep: bool) -> None:
    import miniaudio

    print(os.getpid(), flush=True)  # a venv's python.exe is a launcher: say who really plays

    if beep:
        import winsound

        for _ in range(3):
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            time.sleep(0.8)
        return

    def frames() -> Any:
        n = 0
        required = yield b""
        while True:
            buf = array.array("h", bytes(required * 4))
            for i in range(required):
                v = int(320 * math.sin(2 * math.pi * 440 * (n + i) / RATE))
                buf[2 * i] = v
                buf[2 * i + 1] = v
            n += required
            required = yield buf

    device = miniaudio.PlaybackDevice(
        output_format=miniaudio.SampleFormat.SIGNED16, nchannels=2, sample_rate=RATE
    )
    gen = frames()
    next(gen)
    device.start(gen)
    time.sleep(seconds)
    device.close()


# ---- capture ----------------------------------------------------------------------------


class Capture:
    """Loopback of the default output; `exclude_pid` switches to process loopback."""

    def __init__(self, exclude_pid: int | None) -> None:
        import _miniaudio
        import miniaudio

        ffi, lib = _miniaudio.ffi, _miniaudio.lib
        self.peak = 0
        self.sum_sq = 0.0
        self.count = 0
        outer = self

        class _Loopback(miniaudio.CaptureDevice):
            def __init__(self) -> None:
                miniaudio.AbstractDevice.__init__(self)
                self.format = miniaudio.SampleFormat.SIGNED16
                self.sample_width = 2
                self.nchannels = 2
                self.buffersize_msec = 10
                self._ffi_handle = ffi.new_handle(self)
                config = lib.ma_device_config_init(lib.ma_device_type_loopback)
                config.sampleRate = RATE
                config.capture.channels = 2
                config.capture.format = self.format.value
                config.capture.pDeviceID = ffi.NULL
                config.periodSizeInMilliseconds = 10
                if exclude_pid is not None:
                    config.wasapi.loopbackProcessID = exclude_pid
                    config.wasapi.loopbackProcessExclude = 1
                config.pUserData = self._ffi_handle
                config.dataCallback = lib._internal_data_callback
                config.stopCallback = lib._internal_stop_callback
                self._devconfig = config
                self.callback_generator = None
                self._context = self._make_context([miniaudio.Backend.WASAPI])
                result = lib.ma_device_init(
                    self._context, ffi.addressof(self._devconfig), self._device
                )
                if result != lib.MA_SUCCESS:
                    raise miniaudio.MiniaudioError("loopback init failed", result)

        def consumer() -> Any:
            while True:
                data = yield
                samples = array.array("h", bytes(data))
                for s in samples:
                    a = abs(s)
                    if a > outer.peak:
                        outer.peak = a
                    outer.sum_sq += s * s
                outer.count += len(samples)

        gen = consumer()
        next(gen)
        if exclude_pid is not None:
            # Tandem's own capture (miniaudio's switch for this fails on desktop Windows).
            import importlib.util
            from pathlib import Path

            path = Path(__file__).parents[1] / "src/tandem/engine/adapters/process_loopback.py"
            spec = importlib.util.spec_from_file_location("process_loopback", path)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._device = module.ProcessLoopbackCapture(exclude_pid)
            self._device.start(lambda pcm: gen.send(pcm))
        else:
            self._device = _Loopback()
            self._device.start(gen)

    def close(self) -> tuple[int, float]:
        stop = getattr(self._device, "stop", None)
        if stop is not None:
            stop()
        else:
            self._device.close()
        rms = math.sqrt(self.sum_sq / self.count) if self.count else 0.0
        return self.peak, rms


# ---- Core Audio through raw COM vtables (no comtypes needed) ------------------------------

ole32 = ctypes.OleDLL("ole32")


class GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_byte * 16)]

    @classmethod
    def of(cls, text: str) -> GUID:
        g = cls()
        ctypes.memmove(g.data, uuid.UUID(text).bytes_le, 16)
        return g


CLSID_MMDeviceEnumerator = GUID.of("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_IMMDeviceEnumerator = GUID.of("A95664D2-9614-4F35-A746-DE8DB63617E6")
IID_IAudioEndpointVolume = GUID.of("5CDF2C82-841E-4546-9722-0CF74078229A")
IID_IAudioSessionManager2 = GUID.of("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F")
IID_IAudioSessionControl2 = GUID.of("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D")
IID_ISimpleAudioVolume = GUID.of("87CE5498-68D6-44E5-9215-6F031C6F3E13")
CLSCTX_ALL = 23


def call(obj: c_void_p, index: int, *args: Any, argtypes: tuple[Any, ...] = ()) -> int:
    vtable = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)(vtable[index])
    return fn(obj, *args)


def release(obj: c_void_p) -> None:
    vtable = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    ctypes.WINFUNCTYPE(c_uint, c_void_p)(vtable[2])(obj)


def default_device() -> c_void_p:
    ole32.CoInitializeEx(None, 0)
    enum = c_void_p()
    ole32.CoCreateInstance(
        byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL, byref(IID_IMMDeviceEnumerator), byref(enum)
    )
    device = c_void_p()
    # GetDefaultAudioEndpoint(eRender=0, eConsole=0)
    call(enum, 4, 0, 0, byref(device), argtypes=(c_int, c_int, POINTER(c_void_p)))
    release(enum)
    return device


def activate(device: c_void_p, iid: GUID) -> c_void_p:
    out = c_void_p()
    call(device, 3, byref(iid), CLSCTX_ALL, None, byref(out),
         argtypes=(POINTER(GUID), c_uint, c_void_p, POINTER(c_void_p)))
    return out


def endpoint_mute(volume: c_void_p) -> bool:
    muted = wintypes.BOOL()
    call(volume, 15, byref(muted), argtypes=(POINTER(wintypes.BOOL),))
    return bool(muted.value)


def set_endpoint_mute(volume: c_void_p, on: bool) -> None:
    call(volume, 14, on, None, argtypes=(wintypes.BOOL, c_void_p))


def sessions(device: c_void_p) -> list[tuple[int, bool, c_void_p]]:
    """(pid, is system sounds, ISimpleAudioVolume) for each session on the device."""
    manager = activate(device, IID_IAudioSessionManager2)
    enum = c_void_p()
    call(manager, 5, byref(enum), argtypes=(POINTER(c_void_p),))
    count = c_int()
    call(enum, 3, byref(count), argtypes=(POINTER(c_int),))
    found = []
    for i in range(count.value):
        control = c_void_p()
        call(enum, 4, i, byref(control), argtypes=(c_int, POINTER(c_void_p)))
        control2 = c_void_p()
        call(control, 0, byref(IID_IAudioSessionControl2), byref(control2),
             argtypes=(POINTER(GUID), POINTER(c_void_p)))
        pid = wintypes.DWORD()
        call(control2, 14, byref(pid), argtypes=(POINTER(wintypes.DWORD),))
        system = call(control2, 15) == 0  # S_OK means it is the system sounds session
        simple = c_void_p()
        try:
            call(control2, 0, byref(IID_ISimpleAudioVolume), byref(simple),
                 argtypes=(POINTER(GUID), POINTER(c_void_p)))
        except OSError:
            continue  # some sessions don't offer a volume
        found.append((pid.value, system, simple))
    return found


def session_mute(simple: c_void_p) -> bool:
    muted = wintypes.BOOL()
    call(simple, 6, byref(muted), argtypes=(POINTER(wintypes.BOOL),))
    return bool(muted.value)


def set_session_mute(simple: c_void_p, on: bool) -> None:
    call(simple, 5, on, None, argtypes=(wintypes.BOOL, c_void_p))


# ---- the run ----------------------------------------------------------------------------


def child(beep: bool = False) -> subprocess.Popen[bytes]:
    args = [sys.executable, __file__, "--child", str(TONE_SECONDS)]
    if beep:
        args.append("--beep")
    return subprocess.Popen(args, stdout=subprocess.PIPE)


def measure(label: str, exclude: bool, *, mute_child_session: bool = False,
            beep: bool = False, mute_system: bool = False) -> None:
    device = default_device()
    proc = child(beep)
    assert proc.stdout is not None
    player = int(proc.stdout.readline())
    muted_here: list[c_void_p] = []
    if mute_child_session or mute_system:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not muted_here:
            for pid, system, simple in sessions(device):
                if (mute_child_session and pid == player) or (mute_system and system):
                    if not session_mute(simple):
                        set_session_mute(simple, True)
                        muted_here.append(simple)
            time.sleep(0.05)
    time.sleep(0.3)
    capture = Capture(os.getpid() if exclude else None)
    proc.wait()
    peak, rms = capture.close()
    for simple in muted_here:
        set_session_mute(simple, False)
    found = "session muted" if muted_here else ("no session found" if (mute_child_session or mute_system) else "")
    print(f"{label:58s} peak={peak:6d} rms={rms:8.1f} {found}")


def main() -> None:
    if "--child" in sys.argv:
        play_tone(float(sys.argv[sys.argv.index("--child") + 1]), "--beep" in sys.argv)
        return
    print(f"Windows build {sys.getwindowsversion().build}; tone peak should read about 320")
    device = default_device()
    volume = activate(device, IID_IAudioEndpointVolume)
    was_muted = endpoint_mute(volume)
    try:
        set_endpoint_mute(volume, True)
        measure("1. classic loopback, speakers muted", False)
        measure("2. process loopback, speakers muted", True)
        set_endpoint_mute(volume, was_muted)
        measure("3. process loopback, tone app's session muted", True, mute_child_session=True)
        measure("4. classic loopback, tone app's session muted", False, mute_child_session=True)
        set_endpoint_mute(volume, True)
        measure("5. process loopback, system beep, speakers muted", True, beep=True)
        measure("6. process loopback, system beep, system sounds muted", True, beep=True, mute_system=True)
    finally:
        set_endpoint_mute(volume, was_muted)
        print("speaker mute restored")


if __name__ == "__main__":
    main()
