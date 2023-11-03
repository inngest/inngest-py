from __future__ import annotations

import inspect
import typing

from inngest._internal import errors, execution, result, transforms, types

from .log import LoggerMiddleware
from .middleware import Middleware, MiddlewareSync

# Prevent circular import
if typing.TYPE_CHECKING:
    from inngest._internal import client_lib


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

    async def after_execution(self) -> None:
        for m in self._middleware:
            await transforms.maybe_await(m.after_execution())

    def after_execution_sync(self) -> result.MaybeError[None]:
        for m in self._middleware:
            if inspect.iscoroutinefunction(m.after_execution):
                return result.Err(_mismatched_sync)
            m.after_execution()
        return result.Ok(None)

    async def before_execution(self) -> None:
        method_name = inspect.currentframe().f_code.co_name  # type: ignore
        if method_name in self._disabled_methods:
            return None

        for m in self._middleware:
            await transforms.maybe_await(m.before_execution())
        self._disabled_methods.add(method_name)

    def before_execution_sync(self) -> result.MaybeError[None]:
        method_name = inspect.currentframe().f_code.co_name  # type: ignore
        if method_name in self._disabled_methods:
            return result.Ok(None)

        for m in self._middleware:
            if inspect.iscoroutinefunction(m.before_execution):
                return result.Err(_mismatched_sync)
            m.before_execution()
        self._disabled_methods.add(method_name)
        return result.Ok(None)

    async def before_response(self) -> None:
        for m in self._middleware:
            await transforms.maybe_await(m.before_response())

    def before_response_sync(self) -> result.MaybeError[None]:
        for m in self._middleware:
            if inspect.iscoroutinefunction(m.before_response):
                return result.Err(_mismatched_sync)
            m.before_response()
        return result.Ok(None)

    async def transform_input(
        self,
        call_input: execution.TransformableCallInput,
    ) -> execution.TransformableCallInput:
        for m in self._middleware:
            call_input = await transforms.maybe_await(
                m.transform_input(call_input),
            )
        return call_input

    def transform_input_sync(
        self,
        call_input: execution.TransformableCallInput,
    ) -> result.MaybeError[execution.TransformableCallInput]:
        for m in self._middleware:
            if isinstance(m, Middleware):
                return result.Err(_mismatched_sync)

            call_input = m.transform_input(call_input)
        return result.Ok(call_input)

    async def transform_output(
        self,
        output: types.Serializable,
    ) -> types.Serializable:
        for m in self._middleware:
            output = await transforms.maybe_await(m.transform_output(output))
        return output

    def transform_output_sync(
        self,
        output: types.Serializable,
    ) -> result.MaybeError[types.Serializable]:
        for m in self._middleware:
            if isinstance(m, Middleware):
                return result.Err(_mismatched_sync)

            output = m.transform_output(output)
        return result.Ok(output)
