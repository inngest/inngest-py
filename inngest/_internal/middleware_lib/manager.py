from __future__ import annotations

import inspect
import typing

from inngest._internal import (
    client_lib,
    errors,
    execution,
    result,
    transforms,
    types,
)

from .log import LoggerMiddleware
from .middleware import Middleware, MiddlewareSync

MiddlewareT = typing.TypeVar("MiddlewareT", bound=Middleware)
MiddlewareSyncT = typing.TypeVar("MiddlewareSyncT", bound=MiddlewareSync)


_mismatched_sync = errors.MismatchedSync(
    "encountered async middleware in non-async context"
)

DEFAULT_MIDDLEWARE: list[typing.Type[Middleware | MiddlewareSync]] = [
    LoggerMiddleware
]


class MiddlewareManager:
    def __init__(self, client: client_lib.Inngest) -> None:
        middleware = [
            *client.middleware,
            *DEFAULT_MIDDLEWARE,
        ]
        self._middleware = [m(client) for m in middleware]

        self._disabled_methods = set[str]()

    def add(self, middleware: Middleware | MiddlewareSync) -> None:
        self._middleware = [*self._middleware, middleware]

    async def after_execution(self) -> result.MaybeError[None]:
        try:
            for m in self._middleware:
                await transforms.maybe_await(m.after_execution())
            return result.Ok(None)
        except Exception as err:
            return result.Err(err)

    def after_execution_sync(self) -> result.MaybeError[None]:
        try:
            for m in self._middleware:
                if inspect.iscoroutinefunction(m.after_execution):
                    return result.Err(_mismatched_sync)
                m.after_execution()
            return result.Ok(None)
        except Exception as err:
            return result.Err(err)

    async def before_execution(self) -> result.MaybeError[None]:
        try:
            method_name = inspect.currentframe().f_code.co_name  # type: ignore
            if method_name in self._disabled_methods:
                return result.Ok(None)

            for m in self._middleware:
                await transforms.maybe_await(m.before_execution())
            self._disabled_methods.add(method_name)
            return result.Ok(None)
        except Exception as err:
            return result.Err(err)

    def before_execution_sync(self) -> result.MaybeError[None]:
        try:
            method_name = inspect.currentframe().f_code.co_name  # type: ignore
            if method_name in self._disabled_methods:
                return result.Ok(None)

            for m in self._middleware:
                if inspect.iscoroutinefunction(m.before_execution):
                    return result.Err(_mismatched_sync)
                m.before_execution()
            self._disabled_methods.add(method_name)
            return result.Ok(None)
        except Exception as err:
            return result.Err(err)

    async def before_response(self) -> result.MaybeError[None]:
        try:
            for m in self._middleware:
                await transforms.maybe_await(m.before_response())
            return result.Ok(None)
        except Exception as err:
            return result.Err(err)

    def before_response_sync(self) -> result.MaybeError[None]:
        try:
            for m in self._middleware:
                if inspect.iscoroutinefunction(m.before_response):
                    return result.Err(_mismatched_sync)
                m.before_response()
            return result.Ok(None)
        except Exception as err:
            return result.Err(err)

    async def transform_input(
        self,
        call_input: execution.TransformableCallInput,
    ) -> result.MaybeError[execution.TransformableCallInput]:
        try:
            for m in self._middleware:
                call_input = await transforms.maybe_await(
                    m.transform_input(call_input),
                )
            return result.Ok(call_input)
        except Exception as err:
            return result.Err(err)

    def transform_input_sync(
        self,
        call_input: execution.TransformableCallInput,
    ) -> result.MaybeError[execution.TransformableCallInput]:
        try:
            for m in self._middleware:
                if isinstance(m, Middleware):
                    return result.Err(_mismatched_sync)
                call_input = m.transform_input(call_input)
            return result.Ok(call_input)
        except Exception as err:
            return result.Err(err)

    async def transform_output(
        self,
        output: types.Serializable,
    ) -> result.MaybeError[types.Serializable]:
        try:
            for m in self._middleware:
                output = await transforms.maybe_await(
                    m.transform_output(output)
                )
            return result.Ok(output)
        except Exception as err:
            return result.Err(err)

    def transform_output_sync(
        self,
        output: types.Serializable,
    ) -> result.MaybeError[types.Serializable]:
        try:
            for m in self._middleware:
                if isinstance(m, Middleware):
                    return result.Err(_mismatched_sync)
                output = m.transform_output(output)
            return result.Ok(output)
        except Exception as err:
            return result.Err(err)
