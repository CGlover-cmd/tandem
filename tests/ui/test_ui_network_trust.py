"""Whether Windows trusts the network (Private) or not (Public), as the window shows it."""

from __future__ import annotations

import asyncio

from tandem.bridge import DemoBackend
from tandem.ui.controller import AppController
from tandem.ui.network_trust import NetworkWatch, untrusted


def test_only_all_public_networks_are_untrusted() -> None:
    assert untrusted(["public"])
    assert untrusted(["public", "public"])
    assert not untrusted(["public", "private"])  # e.g. Ethernet at home plus a VPN
    assert not untrusted(["domain"])
    assert not untrusted([])  # offline: nothing to say
    assert not untrusted(None)  # couldn't tell


async def test_the_window_shows_an_untrusted_network_and_opens_settings(
    backend: DemoBackend,
) -> None:
    categories: list[list[str] | None] = [["public"]]
    opened: list[bool] = []
    watch = NetworkWatch(check=lambda: categories[-1], open_settings=lambda: opened.append(True))
    controller = AppController(backend, network=watch)
    changes: list[int] = []
    controller.subscribe(lambda: changes.append(1))
    await controller.start()
    for _ in range(50):
        if controller.snapshot()["network"]["untrusted"]:
            break
        await asyncio.sleep(0.01)
    assert controller.snapshot()["network"] == {"untrusted": True}

    controller.handle({"type": "openNetworkSettings"})
    assert opened == [True]

    categories.append(["private"])  # the user marked it Private
    assert await watch.refresh()
    assert controller.snapshot()["network"] == {"untrusted": False}
    assert not await watch.refresh()  # no change
    await controller.stop()


async def test_no_watch_means_nothing_to_show(backend: DemoBackend) -> None:
    controller = AppController(backend)
    controller.handle({"type": "openNetworkSettings"})  # ignored
    assert controller.snapshot()["network"] == {"untrusted": False}
