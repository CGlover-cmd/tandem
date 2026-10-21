"""Tandem's interface: PySide6 + QML (ADR-0002).

The UI never imports engine code. It talks to the engine through the `Backend` protocol in
`tandem.ui.backend`; `DemoBackend` stands in until the engine adapter exists.
"""
