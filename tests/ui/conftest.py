from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tandem.ui.demo_backend import DemoBackend
from tandem.ui.platform import add_qt_dll_directory

add_qt_dll_directory()


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    return app


async def _no_wait(_seconds: float) -> None:
    await asyncio.sleep(0)


@pytest.fixture
def backend() -> DemoBackend:
    """A demo backend whose delays take no time."""
    return DemoBackend(sleep=_no_wait)
