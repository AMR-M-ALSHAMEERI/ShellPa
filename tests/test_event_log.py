import json
from pathlib import Path

from shellpa.event_log import SessionLogger, logging_enabled


def read_events(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_logger_writes_only_allowlisted_metadata(tmp_path: Path) -> None:
    path = tmp_path / "logs" / "shellpa.jsonl"
    logger = SessionLogger(path, enabled=True)

    written = logger.emit(
        "execution_completed",
        success=False,
        exit_code=1,
        duration_ms=25,
        timed_out=False,
        cancelled=False,
        output_truncated=False,
        partial_effect_possible=True,
        query="delete my files",
        command="Remove-Item secret.txt",
        stdout="OPENAI_API_KEY=sk-supersecret123",
    )

    assert written is True
    [event] = read_events(path)
    assert event["event"] == "execution_completed"
    assert event["success"] is False
    assert event["exit_code"] == 1
    assert "query" not in event
    assert "command" not in event
    assert "stdout" not in event
    assert "delete my files" not in path.read_text(encoding="utf-8")
    assert "supersecret" not in path.read_text(encoding="utf-8")


def test_unknown_events_are_not_written(tmp_path: Path) -> None:
    path = tmp_path / "shellpa.jsonl"
    logger = SessionLogger(path, enabled=True)

    assert logger.emit("raw_debug", query="private intent") is False
    assert not path.exists()


def test_disabled_logger_creates_no_file(tmp_path: Path) -> None:
    path = tmp_path / "shellpa.jsonl"
    logger = SessionLogger(path, enabled=False)

    assert logger.emit("session_start", version="0.2.0") is False
    assert not path.exists()


def test_logging_environment_opt_out() -> None:
    assert logging_enabled({"SHELLPA_LOGGING": "off"}) is False
    assert logging_enabled({"SHELLPA_LOGGING": "FALSE"}) is False
    assert logging_enabled({}) is True


def test_logging_failure_never_raises(tmp_path: Path) -> None:
    occupied_path = tmp_path / "occupied"
    occupied_path.write_text("not a directory", encoding="utf-8")
    logger = SessionLogger(occupied_path / "shellpa.jsonl", enabled=True)

    assert logger.emit("session_start", version="0.2.0") is False
    assert logger.last_error is not None


def test_string_metadata_is_defensively_redacted(tmp_path: Path) -> None:
    path = tmp_path / "shellpa.jsonl"
    logger = SessionLogger(path, enabled=True)

    logger.emit(
        "session_start",
        version="0.2.0",
        provider="openai",
        model="OPENAI_API_KEY=sk-privatevalue123",
        os="Windows",
        shell="PowerShell",
        mode="ask",
    )

    text = path.read_text(encoding="utf-8")
    assert "privatevalue" not in text
    assert "<REDACTED>" in text
