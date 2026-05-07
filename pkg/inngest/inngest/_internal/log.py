from __future__ import annotations

import collections.abc
import logging
import types as py_types
import typing
from contextvars import ContextVar

from . import types as inngest_types

if typing.TYPE_CHECKING:
    _LoggerAdapterBase = logging.LoggerAdapter[logging.Logger]
else:
    _LoggerAdapterBase = logging.LoggerAdapter

_ExcInfo: typing.TypeAlias = (
    bool
    | BaseException
    | tuple[type[BaseException], BaseException, py_types.TracebackType | None]
    | tuple[None, None, None]
    | None
)

# ContextVar for async/thread-safe enable/disable state
_logging_enabled: ContextVar[bool] = ContextVar(
    "inngest_logging_enabled", default=False
)


def enable_logging() -> None:
    _logging_enabled.set(True)


def disable_logging() -> None:
    _logging_enabled.set(False)


class FilteredLogger(_LoggerAdapterBase):
    """
    Wrapper that intercepts logging calls to prevent duplicates during step replay.
    Uses ContextVar for async/thread safety.
    """

    def __init__(self, logger: inngest_types.Logger) -> None:
        super().__init__(typing.cast(logging.Logger, logger), {})

    def log(
        self,
        level: int,
        msg: object,
        *args: object,
        exc_info: _ExcInfo = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        extra: collections.abc.Mapping[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        if not _logging_enabled.get():
            return

        super().log(
            level,
            msg,
            *args,
            exc_info=exc_info,
            stack_info=stack_info,
            stacklevel=stacklevel,
            extra=extra,
            **kwargs,
        )

    def process(
        self,
        msg: object,
        kwargs: typing.MutableMapping[str, object],
    ) -> tuple[object, typing.MutableMapping[str, object]]:
        return msg, kwargs


class ContextLogger(_LoggerAdapterBase):
    """
    Wrapper that adds execution metadata to log records.
    """

    def __init__(
        self,
        logger: inngest_types.Logger,
        extra: collections.abc.Mapping[str, object],
    ) -> None:
        super().__init__(typing.cast(logging.Logger, logger), {})
        self._context_extra = dict(extra)

    def process(
        self,
        msg: object,
        kwargs: typing.MutableMapping[str, object],
    ) -> tuple[object, typing.MutableMapping[str, object]]:
        extra: dict[str, object] = {}
        existing = kwargs.get("extra")
        if isinstance(existing, collections.abc.Mapping):
            for key, value in existing.items():
                if isinstance(key, str):
                    extra[key] = value

        extra.update(self._context_extra)
        kwargs["extra"] = extra
        return msg, kwargs
