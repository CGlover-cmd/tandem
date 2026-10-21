"""Structured, redacted logging.

Log files are JSON lines (one object per record) in the app's log folder, rotated by size.
Every line, console or file, goes through the `Redactor` first, so device names, addresses
and identifiers never reach disk or a terminal (docs/PRIVACY.md).
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from pathlib import Path

from tandem.engine.redact import Redactor

LOG_FILE_NAME = "tandem.log"
_MAX_BYTES = 1_000_000
_BACKUPS = 5


class RedactingFormatter(logging.Formatter):
    """Human-readable lines for the console, redacted."""

    def __init__(self, redactor: Redactor, fmt: str | None = None) -> None:
        super().__init__(fmt or "%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        self._redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        return self._redactor.redact(super().format(record))


class JsonFormatter(logging.Formatter):
    """One JSON object per line: ts, level, logger, msg and (if any) exc. Redacted."""

    def __init__(self, redactor: Redactor) -> None:
        super().__init__()
        self._redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, str] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": self._redactor.redact(record.getMessage()),
        }
        if record.exc_info:
            entry["exc"] = self._redactor.redact(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(
    redactor: Redactor,
    *,
    log_dir: Path | None = None,
    level: int = logging.INFO,
    console: bool = True,
    console_level: int = logging.WARNING,
) -> None:
    """Send the `tandem` logger (and pyatv's) to a redacted file and/or the console.

    Replaces handlers from any earlier call, so it is safe to call again.
    """
    handlers: list[logging.Handler] = []
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / LOG_FILE_NAME, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
        )
        file_handler.setFormatter(JsonFormatter(redactor))
        file_handler.setLevel(level)
        handlers.append(file_handler)
    if console:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(RedactingFormatter(redactor))
        stream.setLevel(console_level)
        handlers.append(stream)

    for name in ("tandem", "pyatv"):
        logger = logging.getLogger(name)
        for old in list(logger.handlers):
            if getattr(old, "_tandem_handler", False):
                logger.removeHandler(old)
                old.close()
        logger.setLevel(min(level, console_level) if console else level)
        logger.propagate = False
        for handler in handlers:
            handler._tandem_handler = True  # type: ignore[attr-defined]
            logger.addHandler(handler)
