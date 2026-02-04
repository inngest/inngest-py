from __future__ import annotations

from contextvars import ContextVar

from . import types

# ContextVar for async/thread-safe enable/disable state
_logging_enabled: ContextVar[bool] = ContextVar(
    "inngest_logging_enabled", default=False
)


def enable_logging() -> None:
    _logging_enabled.set(True)


def disable_logging() -> None:
    _logging_enabled.set(False)


class FilteredLogger:
    """
    Wrapper that intercepts logging calls to prevent duplicates during step replay.
    Uses ContextVar for async/thread safety.
    """

    _proxied_methods = (
        "critical",
        "debug",
        "error",
        "exception",
        "fatal",
        "info",
        "log",
        "warn",
        "warning",
    )

    def __init__(self, logger: types.Logger) -> None:
        self._logger = logger

    def __getattr__(self, name: str) -> object:
        if name in self._proxied_methods and not _logging_enabled.get():
            # Return noop when logging is disabled
            return lambda *args, **kwargs: None

        return getattr(self._logger, name)
