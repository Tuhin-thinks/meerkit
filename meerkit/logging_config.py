import json
import logging
import re
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from meerkit.logging_context import get_context

_CONFIGURED = False
_REGISTERED_HANDLERS: list[logging.Handler] = []

_REDACTED = "***REDACTED***"
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(session|sessionid|session_id|csrf|csrftoken|x-csrftoken|authorization|cookie)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"(sessionid=)([^;\s]+)", re.IGNORECASE),
    re.compile(r"(csrftoken=)([^;\s]+)", re.IGNORECASE),
    re.compile(r"(authorization:\s*)(.+)", re.IGNORECASE),
]


class ContextFilter(logging.Filter):
    """Inject request/worker contextvars into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.context = dict(get_context())
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, *, redact_sensitive_fields: bool) -> None:
        super().__init__()
        self._redact_sensitive_fields = redact_sensitive_fields

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self._sanitize(record.getMessage()),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread_name": record.threadName,
            "process": record.process,
            "context": self._sanitize(getattr(record, "context", {})),
            "metrics": self._sanitize(getattr(record, "metrics", {})),
            "event": getattr(record, "event", None),
        }

        extra = self._extract_extra_fields(record)
        if extra:
            payload["extra"] = self._sanitize(extra)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True, default=str)

    def _extract_extra_fields(self, record: logging.LogRecord) -> dict[str, Any]:
        reserved_keys = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "asctime",
            "context",
            "metrics",
            "event",
        }
        return {
            key: value
            for key, value in record.__dict__.items()
            if key not in reserved_keys and not key.startswith("_")
        }

    def _sanitize(self, value: Any) -> Any:
        if not self._redact_sensitive_fields:
            return value

        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, inner_value in value.items():
                if _SENSITIVE_KEY_PATTERN.search(str(key)):
                    sanitized[key] = _REDACTED
                else:
                    sanitized[key] = self._sanitize(inner_value)
            return sanitized

        if isinstance(value, list):
            return [self._sanitize(item) for item in value]

        if isinstance(value, tuple):
            return tuple(self._sanitize(item) for item in value)

        if isinstance(value, str):
            result = value
            for pattern in _SENSITIVE_VALUE_PATTERNS:
                result = pattern.sub(r"\1" + _REDACTED, result)
            return result

        return value


def _build_handlers(
    *,
    log_file_path: str,
    max_bytes: int,
    backup_count: int,
    redact_sensitive_fields: bool,
) -> list[logging.Handler]:
    formatter = JsonFormatter(redact_sensitive_fields=redact_sensitive_fields)
    context_filter = ContextFilter()

    handlers: list[logging.Handler] = []

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)
    handlers.append(console_handler)

    file_path = Path(log_file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    rotating_file_handler = RotatingFileHandler(
        filename=file_path,
        maxBytes=max(1, int(max_bytes)),
        backupCount=max(1, int(backup_count)),
        encoding="utf-8",
    )
    rotating_file_handler.setFormatter(formatter)
    rotating_file_handler.addFilter(context_filter)
    handlers.append(rotating_file_handler)

    return handlers


def _suppress_loggers(logger_names: list[str]) -> None:
    for logger_name in logger_names:
        normalized_name = str(logger_name).strip()
        if not normalized_name:
            continue
        noisy_logger = logging.getLogger(normalized_name)
        noisy_logger.handlers.clear()
        noisy_logger.propagate = False
        noisy_logger.disabled = True


def setup_logging(
    *,
    enabled: bool,
    log_level: str,
    log_file_path: str,
    max_bytes: int,
    backup_count: int,
    redact_sensitive_fields: bool,
    suppressed_loggers: list[str] | None = None,
    additional_handlers: list[logging.Handler] | None = None,
) -> None:
    """Configure root logging once with JSON output and rotating files."""
    global _CONFIGURED

    if _CONFIGURED or not enabled:
        return

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, str(log_level).upper(), logging.INFO))

    handlers = _build_handlers(
        log_file_path=log_file_path,
        max_bytes=max_bytes,
        backup_count=backup_count,
        redact_sensitive_fields=redact_sensitive_fields,
    )
    if additional_handlers:
        handlers.extend(additional_handlers)
    handlers.extend(_REGISTERED_HANDLERS)

    for handler in handlers:
        root_logger.addHandler(handler)

    _suppress_loggers(suppressed_loggers or [])

    _CONFIGURED = True


def register_handler(handler: logging.Handler) -> None:
    """Register an extra sink handler for future integrations (e.g. Elasticsearch)."""
    _REGISTERED_HANDLERS.append(handler)
    if _CONFIGURED:
        logging.getLogger().addHandler(handler)
