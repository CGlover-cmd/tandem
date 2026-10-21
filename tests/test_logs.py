from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from tandem.engine.logs import LOG_FILE_NAME, configure_logging
from tandem.engine.redact import Redactor


def _records(log_dir: Path) -> list[dict[str, str]]:
    lines = (log_dir / LOG_FILE_NAME).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_file_log_is_redacted_json(tmp_path: Path) -> None:
    redactor = Redactor()
    redactor.add("Living Room Speaker")
    configure_logging(redactor, log_dir=tmp_path, console=False)
    logging.getLogger("tandem.test").info(
        "Connected to %s at %s", "Living Room Speaker", "192.0.2.10"
    )
    (record,) = _records(tmp_path)
    assert record["msg"] == "Connected to <device-1> at <ip-1>"
    assert record["level"] == "INFO"
    assert record["logger"] == "tandem.test"
    assert record["ts"].endswith("+00:00")


def test_tracebacks_are_redacted(tmp_path: Path) -> None:
    configure_logging(Redactor(), log_dir=tmp_path, console=False)
    try:
        raise OSError("no route to 192.0.2.10")
    except OSError:
        logging.getLogger("tandem.test").exception("Failed")
    (record,) = _records(tmp_path)
    assert "192.0.2.10" not in record["exc"]
    assert "<ip-1>" in record["exc"]


def test_pyatv_logs_are_captured_too(tmp_path: Path) -> None:
    configure_logging(Redactor(), log_dir=tmp_path, console=False)
    logging.getLogger("pyatv.core").warning("device at 192.0.2.10")
    assert _records(tmp_path)[0]["msg"] == "device at <ip-1>"


def test_console_is_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Redactor(), console=True)
    logging.getLogger("tandem.test").warning("lost AA:BB:CC:00:00:01")
    err = capsys.readouterr().err
    assert "<mac-1>" in err
    assert "AA:BB:CC" not in err


def test_configure_twice_does_not_duplicate_lines(tmp_path: Path) -> None:
    configure_logging(Redactor(), log_dir=tmp_path, console=False)
    configure_logging(Redactor(), log_dir=tmp_path, console=False)
    logging.getLogger("tandem.test").info("once")
    assert len(_records(tmp_path)) == 1


def test_level_filters_file_output(tmp_path: Path) -> None:
    configure_logging(Redactor(), log_dir=tmp_path, console=False, level=logging.WARNING)
    log = logging.getLogger("tandem.test")
    log.info("hidden")
    log.warning("shown")
    assert [r["msg"] for r in _records(tmp_path)] == ["shown"]
