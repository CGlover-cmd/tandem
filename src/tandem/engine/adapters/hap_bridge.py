# pyright: basic
# (HAP-python ships no type information.)
"""The Home bridge's HomeKit side, on HAP-python (Apache-2.0) (Phase 10b, ADR-0016).

HAP-python keeps the bridge's identity and the Home app's pairing keys in a state file. Tandem
encrypts that file with DPAPI, like its other credentials (ADR-0007), so it's only readable by
this Windows user on this PC.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from tandem.engine import dpapi
from tandem.engine.home_bridge import SwitchSpec

HAP_PORT = 51827
_ENTROPY = b"tandem-home-bridge"


class DpapiEncoder:  # pragma: no cover - exercised with HAP-python by hand
    """HAP-python's state encoder, with the JSON encrypted by DPAPI."""

    def persist(self, fp: Any, state: Any) -> None:
        from pyhap.encoder import AccessoryEncoder

        buffer = io.StringIO()
        AccessoryEncoder.persist(buffer, state)
        sealed = dpapi.protect(buffer.getvalue().encode("utf-8"), _ENTROPY)
        fp.write(base64.b64encode(sealed).decode("ascii"))

    def load_into(self, fp: Any, state: Any) -> None:
        from pyhap.encoder import AccessoryEncoder

        sealed = base64.b64decode(fp.read())
        text = dpapi.unprotect(sealed, _ENTROPY).decode("utf-8")
        AccessoryEncoder.load_into(io.StringIO(text), state)


class HapBridgeServer:  # pragma: no cover - needs the network and the Home app
    def __init__(self, state_file: Path, *, port: int = HAP_PORT) -> None:
        self._state_file = state_file
        self._port = port
        self._driver: Any = None
        self._chars: dict[str, Any] = {}

    @property
    def paired(self) -> bool:
        return self._driver is not None and bool(self._driver.state.paired)

    async def start(
        self, switches: Sequence[SwitchSpec], on_set: Callable[[str, bool], None]
    ) -> str:
        import asyncio

        from pyhap.accessory import Accessory, Bridge
        from pyhap.accessory_driver import AccessoryDriver

        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        driver = AccessoryDriver(
            port=self._port,
            persist_file=str(self._state_file),
            encoder=DpapiEncoder(),
            loop=asyncio.get_running_loop(),
        )

        class QuietBridge(Bridge):
            def setup_message(self) -> None:
                pass  # HAP-python prints the setup code; Tandem shows it in Settings instead

        bridge = QuietBridge(driver, "Tandem")
        for spec in switches:
            accessory = Accessory(driver, spec.name)
            service = accessory.add_preload_service("Switch")  # pyright: ignore[reportArgumentType]

            def setter(value: Any, switch_id: str = spec.id) -> None:
                on_set(switch_id, bool(value))

            self._chars[spec.id] = service.configure_char("On", setter_callback=setter)
            bridge.add_accessory(accessory)
        driver.add_accessory(bridge)
        await driver.async_start()
        self._driver = driver
        return driver.state.pincode.decode("ascii")

    async def stop(self) -> None:
        driver, self._driver = self._driver, None
        if driver is not None:
            await driver.async_stop()
        self._chars.clear()

    def set_state(self, switch_id: str, on: bool) -> None:
        char = self._chars.get(switch_id)
        if char is not None:
            char.set_value(on)
