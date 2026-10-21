"""Tandem's interface: a HeroUI web front end in a WebView2 window (ADR-0010).

The UI never imports engine code. It talks to the engine through the `Backend` protocol in
`tandem.ui.backend`; `DemoBackend` stands in until the engine adapter exists. The React
source is in `web/` at the repository root; `server.UiServer` serves its build.
"""
