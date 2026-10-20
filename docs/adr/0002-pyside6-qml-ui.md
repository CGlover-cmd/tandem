# ADR-0002: PySide6 + QML for the interface

- Status: Accepted
- Date: 2026-10-20

## Context
The interface should feel Apple-inspired: rounded geometry, translucency, smooth spring
animations, light and dark mode. It must also be accessible, run in the system tray, and share
a language with the engine.

## Decision
Use Qt 6 through PySide6 (LGPL), with the UI written in QML (Qt Quick) and pure-Python
ViewModels between QML and the engine. The Qt event loop and asyncio are bridged with qasync.

## Consequences
- GPU-accelerated animation and fully custom visual design without a web runtime.
- Qt's accessibility layer maps to Windows UI Automation for screen readers.
- ViewModels are unit-testable without rendering anything.
- LGPL is compatible with this project's GPL-3.0 licence (ADR-0003).
