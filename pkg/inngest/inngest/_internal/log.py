from __future__ import annotations

import collections.abc
import typing
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


# Methods that we want to conditionally proxy to the underlying logger: when
# logging is disabled then noop, else proxy. All other attributes are
# unconditionally proxied.
_LOG_METHODS: typing.Final = (
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


class FilteredLogger:
    """
    Wrapper that intercepts logging calls to prevent duplicates during step
    replay. Uses ContextVar for async/thread safety.

    IMPORTANT: This class must proxy all attributes to the underlying logger. If
    we don't do that, then we can mess up loggers like structlog.

    We intentionally chose a proxy instead of using `logging.Filter` or
    `logging.LoggerAdapter`.
    - Applying a `logging.Filter` would apply our filter logic outside the scope
      of Inngest functions. We don't want to affect their logger in non-Inngest
      contexts.
    - Using a `logging.LoggerAdapter` still has the "must proxy all attributes"
      problem, so it doesn't seem to have a benefit over our proxy pattern.
    """

    def __init__(self, logger: types.Logger) -> None:
        self._logger = logger

    def __getattr__(self, name: str) -> object:
        if name in _LOG_METHODS and not _logging_enabled.get():
            # Return noop when logging is disabled
            return lambda *args, **kwargs: None

        return getattr(self._logger, name)


class ContextLogger:
    """
    Wrapper that adds execution metadata (run_id, request_id, job_id) to log
    records.

    IMPORTANT: This class must proxy all attributes to the underlying logger. If
    we don't do that, then we can mess up loggers like structlog.
    """

    def __init__(
        self,
        logger: types.Logger,
        extra: collections.abc.Mapping[str, object],
    ) -> None:
        self._logger = logger
        self._extra = dict(extra)

    def __getattr__(self, name: str) -> object:
        attr = getattr(self._logger, name)
        if name not in _LOG_METHODS:
            return attr

        context_extra = self._extra

        def wrapper(*args: object, **kwargs: object) -> object:
            # Inngest-injected metadata wins on key collisions. The
            # "inngest.*" namespace is reserved for SDK-managed values; if a
            # caller writes there, they get clobbered to keep correlation
            # IDs in log records authoritative.
            merged: dict[str, object] = {}
            existing = kwargs.get("extra")
            if isinstance(existing, collections.abc.Mapping):
                for key, value in existing.items():
                    if isinstance(key, str):
                        merged[key] = value
            merged.update(context_extra)
            kwargs["extra"] = merged
            return attr(*args, **kwargs)

        return wrapper
