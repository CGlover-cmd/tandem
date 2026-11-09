"""The default microphone, for lining speakers up automatically (`tandem.engine.lineup`).

16 kHz mono 16-bit through miniaudio's own capture device. Recordings stay in memory, are
only used to time Tandem's beeps, and are dropped right after. If Windows doesn't let desktop
apps use the microphone, miniaudio still delivers audio, but silent: the line-up then reports
that it couldn't hear the speakers.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Generator
from typing import Any

from tandem.engine.audio import AudioError
from tandem.engine.lineup import MIC_RATE


class MicrophoneCapture:  # pragma: no cover - needs a microphone
    def __init__(self) -> None:
        self._device: Any = None

    def start(self, on_pcm: Callable[[bytes], None]) -> None:
        if self._device is not None:
            return
        if sys.platform != "win32":
            raise AudioError("the microphone needs Windows")
        import miniaudio

        def collect() -> Generator[None, Any, None]:
            while True:
                data = yield
                on_pcm(bytes(data))

        generator = collect()
        next(generator)
        try:
            device: Any = miniaudio.CaptureDevice(
                input_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=1,
                sample_rate=MIC_RATE,
                buffersize_msec=20,
                app_name="Tandem",
            )
            device.start(generator)
        except miniaudio.MiniaudioError as exc:
            raise AudioError("no microphone") from exc
        self._device = device

    def stop(self) -> None:
        device, self._device = self._device, None
        if device is not None:
            device.close()
