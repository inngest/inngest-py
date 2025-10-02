from __future__ import annotations

import inspect
import typing

from inngest._internal import (
    errors,
    execution_lib,
    function,
    net,
    server_lib,
    step_lib,
    transforms,
    types,
)

from .log import LoggerMiddleware
from .middleware import (
    Middleware,
    MiddlewareSync,
    TransformOutputResult,
    TransformOutputStepInfo,
    UninitializedMiddleware,
)

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

    def __init__(
        self,
        client: client_lib.Inngest,
        raw_request: object,
        timings: net.ServerTimings,
    ) -> None:
        self.client = client
        self._disabled_hooks = set[str]()
        self._middleware = list[typing.Union[Middleware, MiddlewareSync]]()
        self._raw_request = raw_request
        self._timings = timings

    @classmethod
    def from_client(
        cls,
        client: client_lib.Inngest,
        raw_request: object,
        timings: net.ServerTimings | None,
    ) -> MiddlewareManager:
        """
        Create a new manager from an Inngest client, using the middleware on the
        client.
        """

        if timings is None:
            # A dummy timings object to simplify logic
            timings = net.ServerTimings()

        mgr = cls(client, raw_request, timings)

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
        new_mgr = cls(manager.client, manager._raw_request, manager._timings)
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
            # Reverse order because this is an "after" hook.
            for m in reversed(self._middleware):
                await transforms.maybe_await(m.after_execution())
            return None
        except Exception as err:
            return err

    def after_execution_sync(self) -> types.MaybeError[None]:
        try:
            # Reverse order because this is an "after" hook.
            for m in reversed(self._middleware):
                if inspect.iscoroutinefunction(m.after_execution):
                    return _mismatched_sync
                m.after_execution()
            return None
        except Exception as err:
            return err

    async def after_send_events(
        self,
        result: client_lib.SendEventsResult,
    ) -> types.MaybeError[None]:
        try:
            # Reverse order because this is an "after" hook.
            for m in reversed(self._middleware):
                await transforms.maybe_await(m.after_send_events(result))
            return None
        except Exception as err:
            return err

    def after_send_events_sync(
        self,
        result: client_lib.SendEventsResult,
    ) -> types.MaybeError[None]:
        try:
            # Reverse order because this is an "after" hook.
            for m in reversed(self._middleware):
                if inspect.iscoroutinefunction(m.after_execution):
                    return _mismatched_sync
                m.after_send_events(result)
            return None
        except Exception as err:
            return err

    async def before_execution(self) -> types.MaybeError[None]:
        hook = "before_execution"
        if hook in self._disabled_hooks:
            # Only allow before_execution to be called once. This simplifies
            # code since execution can start at the function or step level.
            return None
        self._disabled_hooks.add(hook)

        try:
            for m in self._middleware:
                await transforms.maybe_await(m.before_execution())
        except Exception as err:
            return err

        return None

    def before_execution_sync(self) -> types.MaybeError[None]:
        hook = "before_execution"
        if hook in self._disabled_hooks:
            # Only allow before_execution to be called once. This simplifies
            # code since execution can start at the function or step level.
            return None
        self._disabled_hooks.add(hook)

        try:
            for m in self._middleware:
                if inspect.iscoroutinefunction(m.before_execution):
                    return _mismatched_sync
                m.before_execution()
        except Exception as err:
            return err

        return None

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
        events: list[server_lib.Event],
    ) -> types.MaybeError[None]:
        try:
            for m in self._middleware:
                await transforms.maybe_await(m.before_send_events(events))
            return None
        except Exception as err:
            return err

    def before_send_events_sync(
        self,
        events: list[server_lib.Event],
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
        ctx: typing.Union[execution_lib.Context, execution_lib.ContextSync],
        function: function.Function[typing.Any],
        steps: step_lib.StepMemos,
    ) -> types.MaybeError[None]:
        with self._timings.mw_transform_input:
            try:
                for m in self._middleware:
                    await transforms.maybe_await(
                        m.transform_input(ctx, function, steps),
                    )
            except Exception as err:
                return err

            return None

    def transform_input_sync(
        self,
        ctx: typing.Union[execution_lib.Context, execution_lib.ContextSync],
        function: function.Function[typing.Any],
        steps: step_lib.StepMemos,
    ) -> types.MaybeError[None]:
        with self._timings.mw_transform_input:
            try:
                for m in self._middleware:
                    if inspect.iscoroutinefunction(m.transform_input):
                        return _mismatched_sync
                    m.transform_input(ctx, function, steps)
            except Exception as err:
                return err

            return None

    async def transform_output(
        self,
        call_res: execution_lib.CallResult,
    ) -> types.MaybeError[None]:
        with self._timings.mw_transform_output:
            # This should only happen when planning parallel steps
            if call_res.multi is not None:
                if len(call_res.multi) > 1:
                    return None
                call_res = call_res.multi[0]

            # Not sure how this can happen, but we should handle it
            if call_res.is_empty:
                return None

            # Create a new result object to pass to the middleware. We don't want to
            # pass the CallResult object because it exposes too many internal
            # implementation details
            result = TransformOutputResult(
                error=call_res.error,
                output=call_res.output,
                step=None,
            )
            if call_res.step is not None:
                result.step = TransformOutputStepInfo(
                    id=call_res.step.display_name,
                    op=call_res.step.op,
                    opts=call_res.step.opts,
                )

            try:
                # Reverse order because this is an "after" hook.
                for m in reversed(self._middleware):
                    await transforms.maybe_await(m.transform_output(result))

                # Update the original call result with the (possibly) mutated fields
                call_res.error = result.error
                call_res.output = result.output

                return None
            except Exception as err:
                return err

    def transform_output_sync(
        self,
        call_res: execution_lib.CallResult,
    ) -> types.MaybeError[None]:
        with self._timings.mw_transform_output:
            # This should only happen when planning parallel steps
            if call_res.multi is not None:
                if len(call_res.multi) > 1:
                    return None
                call_res = call_res.multi[0]

            # Not sure how this can happen, but we should handle it
            if call_res.is_empty:
                return None

            # Create a new result object to pass to the middleware. We don't want to
            # pass the CallResult object because it exposes too many internal
            # implementation details
            result = TransformOutputResult(
                error=call_res.error,
                output=call_res.output,
                step=None,
            )
            if call_res.step is not None:
                result.step = TransformOutputStepInfo(
                    id=call_res.step.display_name,
                    op=call_res.step.op,
                    opts=call_res.step.opts,
                )

            try:
                # Reverse order because this is an "after" hook.
                for m in reversed(self._middleware):
                    if isinstance(m, Middleware):
                        return _mismatched_sync
                    m.transform_output(result)

                # Update the original call result with the (possibly) mutated fields
                call_res.error = result.error
                call_res.output = result.output

                return None
            except Exception as err:
                return err
