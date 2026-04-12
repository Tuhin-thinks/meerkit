import contextvars
from collections.abc import Mapping

_LOG_CONTEXT: contextvars.ContextVar[dict[str, object]] = contextvars.ContextVar(
    "meerkit_log_context",
    default={},
)


def bind_context(**values: object) -> None:
    """Merge the provided values into the current logging context."""
    current = dict(_LOG_CONTEXT.get())
    for key, value in values.items():
        if value is None:
            current.pop(key, None)
        else:
            current[key] = value
    _LOG_CONTEXT.set(current)


def clear_context() -> None:
    """Clear all context keys for the current execution context."""
    _LOG_CONTEXT.set({})


def get_context() -> Mapping[str, object]:
    """Return a copy of the current logging context mapping."""
    return dict(_LOG_CONTEXT.get())
