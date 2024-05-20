from __future__ import annotations

import inspect
import typing

from inngest._internal import (
    errors,
    event_lib,
    execution,
    function,
    step_lib,
    transforms,
    types,
)

from .log import LoggerMiddleware
from .middleware import Middleware, MiddlewareSync, UninitializedMiddleware

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib

_mismatched_sync = errors.AsyncUnsupportedError(
    "encountered async middleware in non-async context"
)

DEFAULT_CLIENT_MIDDLEWARE: list[UninitializedMiddleware] = [LoggerMiddleware]


class MiddlewareManager:
    @property
    def middleware(self) -> list[typing.Union[Middleware, MiddlewareSync]]:
        return [*self._middleware]

    def __init__(self, client: client_lib.Inngest, raw_request: object) -> None:
        self.client = client
        self._disabled_hooks = set[str]()
        self._middleware = list[typing.Union[Middleware, MiddlewareSync]]()
        self._raw_request = raw_request

    @classmethod
    def from_client(
        cls,
        client: client_lib.Inngest,
        raw_request: object,
    ) -> MiddlewareManager:
        """
        Create a new manager from an Inngest client, using the middleware on the
        client.
        """
        mgr = cls(client, raw_request)

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
        new_mgr = cls(manager.client, manager._raw_request)
        for m in manager.middleware:
            new_mgr._middleware = [*new_mgr._middleware, m]
        return new_mgr

    def add(self, middleware: UninitializedMiddleware) -> None:
        self._middleware = [
            *self._middleware,
            middleware(self.client, self._raw_request),
        ]

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

    async def before_send_events(
        self,
        events: list[event_lib.Event],
    ) -> types.MaybeError[None]:
        try:
            for m in self._middleware:
                await transforms.maybe_await(m.before_send_events(events))
            return None
        except Exception as err:
            return err

    def before_send_events_sync(
        self,
        events: list[event_lib.Event],
    ) -> types.MaybeError[None]:
        try:
            for m in self._middleware:
                if inspect.iscoroutinefunction(m.before_send_events):
                    return _mismatched_sync
                m.before_send_events(events)
            return None
        except Exception as err:
            return err

    async def transform_input(
        self,
        ctx: function.Context,
        steps: step_lib.StepMemos,
    ) -> types.MaybeError[None]:
        try:
            for m in self._middleware:
                await transforms.maybe_await(
                    m.transform_input(ctx, steps),
                )
            return None
        except Exception as err:
            return err

    def transform_input_sync(
        self,
        ctx: function.Context,
        steps: step_lib.StepMemos,
    ) -> types.MaybeError[None]:
        try:
            for m in self._middleware:
                if isinstance(m, Middleware):
                    return _mismatched_sync
                m.transform_input(ctx, steps)
            return None
        except Exception as err:
            return err

    async def transform_output(
        self,
        call_res: execution.CallResult,
    ) -> types.MaybeError[None]:
        # This should only happen when planning parallel steps
        if call_res.multi is not None:
            if len(call_res.multi) > 1:
                return None
            call_res = call_res.multi[0]

        # Not sure how this can happen, but we should handle it
        if call_res.is_empty:
            return None

        try:
            for m in self._middleware:
                await transforms.maybe_await(m.transform_output(call_res))
            return None
        except Exception as err:
            return err

    def transform_output_sync(
        self,
        call_res: execution.CallResult,
    ) -> types.MaybeError[None]:
        # This should only happen when planning parallel steps
        if call_res.multi is not None:
            if len(call_res.multi) > 1:
                return None
            call_res = call_res.multi[0]

        # Not sure how this can happen, but we should handle it
        if call_res.is_empty:
            return None

        try:
            for m in self._middleware:
                if isinstance(m, Middleware):
                    return _mismatched_sync
                m.transform_output(call_res)
            return None
        except Exception as err:
            return err
