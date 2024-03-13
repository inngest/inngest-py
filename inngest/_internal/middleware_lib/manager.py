from __future__ import annotations

import inspect
import typing

from inngest._internal import (
    client_lib,
    errors,
    execution,
    function,
    transforms,
    types,
)

from .log import LoggerMiddleware
from .middleware import Middleware, MiddlewareSync

MiddlewareT = typing.TypeVar("MiddlewareT", bound=Middleware)
MiddlewareSyncT = typing.TypeVar("MiddlewareSyncT", bound=MiddlewareSync)


_mismatched_sync = errors.AsyncUnsupportedError(
    "encountered async middleware in non-async context"
)

DEFAULT_CLIENT_MIDDLEWARE: list[
    type[typing.Union[Middleware, MiddlewareSync]]
] = [LoggerMiddleware]


class MiddlewareManager:
    @property
    def middleware(self) -> list[typing.Union[Middleware, MiddlewareSync]]:
        return [*self._middleware]

    def __init__(self, client: client_lib.Inngest) -> None:
        self.client = client
        self._disabled_hooks = set[str]()
        self._middleware = list[typing.Union[Middleware, MiddlewareSync]]()

    @classmethod
    def from_client(cls, client: client_lib.Inngest) -> MiddlewareManager:
        """
        Create a new manager from an Inngest client, using the middleware on the
        client.
        """
        mgr = cls(client)

        for m in DEFAULT_CLIENT_MIDDLEWARE:
            mgr.add(m)

        for m in client.middleware:
            mgr.add(m)

        return mgr

    @classmethod
    def from_manager(cls, manager: MiddlewareManager) -> MiddlewareManager:
        """
        Create a new manager from another manager, using the middleware on the
        passed manager. Effectively wraps a manager.
        """
        new_mgr = cls(manager.client)
        for m in manager.middleware:
            new_mgr._middleware = [*new_mgr._middleware, m]
        return new_mgr

    def add(
        self, middleware: type[typing.Union[Middleware, MiddlewareSync]]
    ) -> None:
        self._middleware = [*self._middleware, middleware(self.client)]

    async def after_execution(self) -> types.MaybeError[None]:
        try:
            for m in self._middleware:
                await transforms.maybe_await(m.after_execution())
            return None
        except Exception as err:
            return err

    def after_execution_sync(self) -> types.MaybeError[None]:
        try:
            for m in self._middleware:
                if inspect.iscoroutinefunction(m.after_execution):
                    return _mismatched_sync
                m.after_execution()
            return None
        except Exception as err:
            return err

    async def before_execution(self) -> types.MaybeError[None]:
        hook = "before_execution"
        if hook in self._disabled_hooks:
            # Only allow before_execution to be called once. This simplifies
            # code since execution can start at the function or step level.
            return None

        try:
            for m in self._middleware:
                await transforms.maybe_await(m.before_execution())

            self._disabled_hooks.add(hook)
            return None
        except Exception as err:
            return err

    def before_execution_sync(self) -> types.MaybeError[None]:
        hook = "before_execution"
        if hook in self._disabled_hooks:
            # Only allow before_execution to be called once. This simplifies
            # code since execution can start at the function or step level.
            return None

        try:
            for m in self._middleware:
                if inspect.iscoroutinefunction(m.before_execution):
                    return _mismatched_sync
                m.before_execution()

            self._disabled_hooks.add(hook)
            return None
        except Exception as err:
            return err

    async def before_response(self) -> types.MaybeError[None]:
        try:
            for m in self._middleware:
                await transforms.maybe_await(m.before_response())
            return None
        except Exception as err:
            return err

    def before_response_sync(self) -> types.MaybeError[None]:
        try:
            for m in self._middleware:
                if inspect.iscoroutinefunction(m.before_response):
                    return _mismatched_sync
                m.before_response()
            return None
        except Exception as err:
            return err

    async def transform_input(
        self,
        ctx: function.Context,
    ) -> types.MaybeError[function.Context]:
        try:
            for m in self._middleware:
                ctx = await transforms.maybe_await(
                    m.transform_input(ctx),
                )
            return ctx
        except Exception as err:
            return err

    def transform_input_sync(
        self,
        ctx: function.Context,
    ) -> types.MaybeError[function.Context]:
        try:
            for m in self._middleware:
                if isinstance(m, Middleware):
                    return _mismatched_sync
                ctx = m.transform_input(ctx)
            return ctx
        except Exception as err:
            return err

    async def transform_output(
        self,
        output: typing.Optional[execution.Output],
    ) -> types.MaybeError[typing.Optional[execution.Output]]:
        # Nothing to transform
        if output is None:
            return None

        try:
            for m in self._middleware:
                output = await transforms.maybe_await(
                    m.transform_output(output)
                )
            return output
        except Exception as err:
            return err

    def transform_output_sync(
        self,
        output: typing.Optional[execution.Output],
    ) -> types.MaybeError[typing.Optional[execution.Output]]:
        # Nothing to transform
        if output is None:
            return None

        try:
            for m in self._middleware:
                if isinstance(m, Middleware):
                    return _mismatched_sync
                output = m.transform_output(output)
            return output
        except Exception as err:
            return err
