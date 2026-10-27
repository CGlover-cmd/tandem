"""WASAPI loopback capture of the default output, via miniaudio (Spike C).

miniaudio's Python wrapper has no loopback device class, so this opens one through its C API
(`ma_device_type_loopback`). miniaudio converts the output's own format (usually 48 kHz float)
to 44.1 kHz, 16-bit stereo for AirPlay; Spike C measured that at well under 1% of real time.

Note: on many PCs loopback follows the Windows volume and mute (Spike C, ADR-0005).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Generator
from typing import Any

from tandem.engine.audio import CHANNELS, SAMPLE_RATE, AudioError

_PERIOD_MS = 10


class LoopbackCapture:
    def __init__(self) -> None:
        self._device: Any = None

    def start(self, on_pcm: Callable[[bytes], None]) -> None:
        if self._device is not None:
            return
        if sys.platform != "win32":
            raise AudioError("system audio capture needs Windows")
        import _miniaudio  # pyright: ignore[reportMissingModuleSource]
        import miniaudio  # imported late: only needed while capturing

        ffi: Any = _miniaudio.ffi  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        lib: Any = _miniaudio.lib  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

        class _Loopback(miniaudio.CaptureDevice):
            def __init__(self) -> None:
                miniaudio.AbstractDevice.__init__(self)
                self.format = miniaudio.SampleFormat.SIGNED16
                self.sample_width = 2
                self.nchannels = CHANNELS
                self.buffersize_msec = _PERIOD_MS
                self._ffi_handle = ffi.new_handle(self)
                config: Any = lib.ma_device_config_init(lib.ma_device_type_loopback)
                config.sampleRate = SAMPLE_RATE
                config.capture.channels = CHANNELS
                config.capture.format = self.format.value
                config.capture.pDeviceID = ffi.NULL  # the default output
                config.periodSizeInMilliseconds = _PERIOD_MS
                config.pUserData = self._ffi_handle
                config.dataCallback = lib._internal_data_callback
                config.stopCallback = lib._internal_stop_callback
                self._devconfig = config
                self.callback_generator = None
                self._context = self._make_context([miniaudio.Backend.WASAPI])
                result: Any = lib.ma_device_init(
                    self._context, ffi.addressof(self._devconfig), self._device
                )
                if result != lib.MA_SUCCESS:
                    raise miniaudio.MiniaudioError("failed to open loopback capture", result)

        def consumer() -> Generator[None, Any, None]:
            while True:
                data = yield
                on_pcm(bytes(data))

        try:
            device = _Loopback()
        except Exception as exc:
            raise AudioError(f"can't capture system audio ({type(exc).__name__})") from exc
        generator = consumer()
        next(generator)
        device.start(generator)
        self._device = device

    def stop(self) -> None:
        device, self._device = self._device, None
        if device is not None:
            device.close()
