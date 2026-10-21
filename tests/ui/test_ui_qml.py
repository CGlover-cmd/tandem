"""The QML loads cleanly, and the theme's text colours meet WCAG AA in light and dark mode."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QObject
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlEngine, QQmlError
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication

from tandem.ui.app import QML_DIR, create_engine
from tandem.ui.demo_backend import DemoBackend
from tandem.ui.viewmodels import AppViewModel

AA_TEXT = 4.5


def test_main_window_loads_without_warnings(qapp: QApplication, backend: DemoBackend) -> None:
    warnings: list[str] = []
    vm = AppViewModel(backend, demo_mode=True)
    engine = create_engine(vm)

    def collect(errors: list[QQmlError]) -> None:
        warnings.extend(e.toString() for e in errors)

    engine.warnings.connect(collect)
    qapp.processEvents()

    roots = engine.rootObjects()
    assert len(roots) == 1
    assert isinstance(roots[0], QQuickWindow)
    assert warnings == []
    roots[0].deleteLater()


@pytest.fixture(params=[False, True], ids=["light", "dark"])
def theme(request: pytest.FixtureRequest, qapp: QApplication) -> Iterator[QObject]:
    engine = QQmlEngine()
    errors: list[QQmlError] = []
    engine.warnings.connect(errors.extend)
    engine.addImportPath(str(QML_DIR))
    singleton = engine.singletonInstance("Tandem", "Theme")
    assert isinstance(singleton, QObject), [e.toString() for e in errors]
    singleton.setProperty("dark", request.param)
    yield singleton
    engine.deleteLater()


def _color(theme: QObject, name: str) -> QColor:
    value = theme.property(name)
    assert isinstance(value, QColor), name
    return value


def _over(top: QColor, bottom: QColor) -> QColor:
    a = top.alphaF()
    return QColor.fromRgbF(
        top.redF() * a + bottom.redF() * (1 - a),
        top.greenF() * a + bottom.greenF() * (1 - a),
        top.blueF() * a + bottom.blueF() * (1 - a),
    )


def _luminance(c: QColor) -> float:
    def channel(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(c.redF()) + 0.7152 * channel(c.greenF()) + 0.0722 * channel(c.blueF())


def _contrast(fg: QColor, bg: QColor) -> float:
    hi, lo = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_text_on_cards_meets_aa(theme: QObject) -> None:
    # Worst case behind a card: the window gradient's ends, or a colour wash over the top.
    backdrops = [
        _color(theme, "windowTop"),
        _color(theme, "windowBottom"),
        _over(_color(theme, "blobA"), _color(theme, "windowTop")),
        _over(_color(theme, "blobB"), _color(theme, "windowBottom")),
    ]
    for backdrop in backdrops:
        for surface_name in ("surface", "surfaceHover"):
            surface = _over(_color(theme, surface_name), backdrop)
            for text in ("label", "secondaryLabel", "accent", "success", "warning", "danger"):
                ratio = _contrast(_color(theme, text), surface)
                assert ratio >= AA_TEXT, f"{text} on {surface_name}: {ratio:.2f}"
            tint = _over(_color(theme, "accentTint"), surface)
            assert _contrast(_color(theme, "accent"), tint) >= AA_TEXT


def test_text_on_sheet_and_buttons_meets_aa(theme: QObject) -> None:
    dimmed = _over(_color(theme, "scrim"), _color(theme, "windowBottom"))
    sheet = _over(_color(theme, "sheet"), dimmed)
    for text in ("label", "secondaryLabel", "accent", "danger"):
        assert _contrast(_color(theme, text), sheet) >= AA_TEXT, text
    assert _contrast(_color(theme, "textOnAccent"), _color(theme, "accentFill")) >= AA_TEXT
