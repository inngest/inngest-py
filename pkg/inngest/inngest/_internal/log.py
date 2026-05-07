from __future__ import annotations

import collections.abc
import logging
import typing
from contextvars import ContextVar

from . import types as inngest_types

# ContextVar for async/thread-safe enable/disable state
_logging_enabled: ContextVar[bool] = ContextVar(
    "inngest_logging_enabled", default=False
)


def enable_logging() -> None:
    _logging_enabled.set(True)


def disable_logging() -> None:
    _logging_enabled.set(False)


def _is_stdlib_logger(logger: object) -> bool:
    return isinstance(logger, (logging.Logger, logging.LoggerAdapter))


def _with_adjusted_stacklevel(
    logger: object,
    kwargs: dict[str, object],
) -> dict[str, object]:
    if not _is_stdlib_logger(logger):
        kwargs.pop("stacklevel", None)
        return kwargs

    stacklevel = kwargs.get("stacklevel")
    if not isinstance(stacklevel, int):
        stacklevel = 1
    kwargs["stacklevel"] = stacklevel + 2
    return kwargs


def _merge_extra(
    existing: object,
    context_extra: collections.abc.Mapping[str, object],
) -> dict[str, object]:
    extra: dict[str, object] = {}
    if isinstance(existing, collections.abc.Mapping):
        for key, value in existing.items():
            if isinstance(key, str):
                extra[key] = value

    extra.update(context_extra)
    return extra


def _merge_structured_kwargs(
    kwargs: dict[str, object],
    context_extra: collections.abc.Mapping[str, object],
) -> dict[str, object]:
    merged: dict[str, object] = {}
    existing_extra = kwargs.pop("extra", None)
    if isinstance(existing_extra, collections.abc.Mapping):
        for key, value in existing_extra.items():
            if isinstance(key, str):
                merged[key] = value

    merged.update(kwargs)
    merged.update(context_extra)
    return merged


class FilteredLogger:
    """
    Wrapper that intercepts logging calls to prevent duplicates during step replay.
    Uses ContextVar for async/thread safety.
    """

    def __init__(self, logger: inngest_types.Logger) -> None:
        self._logger = logger

    def critical(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("critical", msg, *args, **kwargs)

    def debug(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("debug", msg, *args, **kwargs)

    def error(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("error", msg, *args, **kwargs)

    def exception(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("exception", msg, *args, **kwargs)

    def fatal(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("fatal", msg, *args, **kwargs)

    def info(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("info", msg, *args, **kwargs)

    def log(
        self,
        level: int,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("log", level, msg, *args, **kwargs)

    def warn(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("warn", msg, *args, **kwargs)

    def warning(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("warning", msg, *args, **kwargs)

    def _call(
        self,
        method: str,
        *args: object,
        **kwargs: object,
    ) -> None:
        if not _logging_enabled.get():
            return

        call_kwargs = dict(kwargs)
        if isinstance(self._logger, ContextLogger):
            stacklevel = call_kwargs.get("stacklevel")
            if not isinstance(stacklevel, int):
                stacklevel = 1
            call_kwargs["stacklevel"] = stacklevel + 2

        fn = typing.cast(
            typing.Callable[..., None], getattr(self._logger, method)
        )
        if isinstance(self._logger, ContextLogger):
            fn(*args, **call_kwargs)
        else:
            fn(*args, **_with_adjusted_stacklevel(self._logger, call_kwargs))


class ContextLogger:
    """
    Wrapper that adds execution metadata to log records.
    """

    def __init__(
        self,
        logger: inngest_types.Logger,
        extra: collections.abc.Mapping[str, object],
    ) -> None:
        self._logger = logger
        self._context_extra = dict(extra)

    def critical(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("critical", msg, *args, **kwargs)

    def debug(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("debug", msg, *args, **kwargs)

    def error(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("error", msg, *args, **kwargs)

    def exception(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("exception", msg, *args, **kwargs)

    def fatal(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("fatal", msg, *args, **kwargs)

    def info(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("info", msg, *args, **kwargs)

    def log(
        self,
        level: int,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("log", level, msg, *args, **kwargs)

    def warn(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("warn", msg, *args, **kwargs)

    def warning(
        self,
        msg: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._call("warning", msg, *args, **kwargs)

    def _call(
        self,
        method: str,
        *args: object,
        **kwargs: object,
    ) -> None:
        kwargs = dict(kwargs)
        if _is_stdlib_logger(self._logger):
            kwargs["extra"] = _merge_extra(
                kwargs.get("extra"),
                self._context_extra,
            )
        else:
            kwargs = _merge_structured_kwargs(kwargs, self._context_extra)

        fn = typing.cast(
            typing.Callable[..., None], getattr(self._logger, method)
        )
        fn(*args, **_with_adjusted_stacklevel(self._logger, kwargs))
