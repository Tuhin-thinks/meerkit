import json
import logging
from pathlib import Path

from meerkit import logging_config


def _reset_logging_state() -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    logging_config._CONFIGURED = False
    logging_config._REGISTERED_HANDLERS.clear()


def _flush_handlers() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_setup_logging_writes_json_with_redaction(tmp_path: Path) -> None:
    _reset_logging_state()
    log_file_path = tmp_path / "app.jsonl"

    logging_config.setup_logging(
        enabled=True,
        log_level="INFO",
        log_file_path=str(log_file_path),
        max_bytes=1024 * 1024,
        backup_count=2,
        redact_sensitive_fields=True,
    )

    logger = logging.getLogger("test_logger")
    logger.info(
        "test_event_message",
        extra={
            "event": "test_event",
            "metrics": {"duration_ms": 12},
            "session_id": "secret-session",
            "response_payload": {"csrf_token": "secret-csrf"},
        },
    )
    _flush_handlers()

    lines = log_file_path.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[-1])

    assert payload["message"] == "test_event_message"
    assert payload["event"] == "test_event"
    assert payload["metrics"]["duration_ms"] == 12
    assert payload["extra"]["session_id"] == "***REDACTED***"
    assert payload["extra"]["response_payload"]["csrf_token"] == "***REDACTED***"


def test_setup_logging_is_idempotent(tmp_path: Path) -> None:
    _reset_logging_state()
    log_file_path = tmp_path / "app.jsonl"

    logging_config.setup_logging(
        enabled=True,
        log_level="INFO",
        log_file_path=str(log_file_path),
        max_bytes=1024 * 1024,
        backup_count=2,
        redact_sensitive_fields=False,
    )
    handler_count_after_first_setup = len(logging.getLogger().handlers)

    logging_config.setup_logging(
        enabled=True,
        log_level="DEBUG",
        log_file_path=str(log_file_path),
        max_bytes=1024 * 1024,
        backup_count=2,
        redact_sensitive_fields=False,
    )

    assert len(logging.getLogger().handlers) == handler_count_after_first_setup


def test_setup_logging_suppresses_noisy_loggers(tmp_path: Path) -> None:
    _reset_logging_state()
    log_file_path = tmp_path / "app.jsonl"

    logging_config.setup_logging(
        enabled=True,
        log_level="DEBUG",
        log_file_path=str(log_file_path),
        max_bytes=1024 * 1024,
        backup_count=2,
        redact_sensitive_fields=False,
        suppressed_loggers=["watchdog.observers.inotify_buffer"],
    )

    logging.getLogger("watchdog.observers.inotify_buffer").info("noisy_event")
    logging.getLogger("app.test").info("normal_event")
    _flush_handlers()

    lines = log_file_path.read_text(encoding="utf-8").strip().splitlines()
    payloads = [json.loads(line) for line in lines if line.strip()]

    assert any(payload["message"] == "normal_event" for payload in payloads)
    assert not any(payload["message"] == "noisy_event" for payload in payloads)
