from __future__ import annotations

import dataclasses
import inspect
import typing
import urllib.parse

import pydantic

from inngest._internal import (
    client_lib,
    const,
    errors,
    event_lib,
    execution,
    function_config,
    middleware_lib,
    step_lib,
    transforms,
    types,
)


@dataclasses.dataclass
class Context:
    attempt: int
    event: event_lib.Event
    events: list[event_lib.Event]
    logger: types.Logger
    run_id: str


@dataclasses.dataclass
class _Config:
    # The user-defined function
    main: function_config.FunctionConfig

    # The internal on_failure function
    on_failure: function_config.FunctionConfig | None


@typing.runtime_checkable
class FunctionHandlerAsync(typing.Protocol):
    def __call__(
        self,
        ctx: Context,
        step: step_lib.Step,
    ) -> typing.Awaitable[types.Serializable]:
        ...


@typing.runtime_checkable
class FunctionHandlerSync(typing.Protocol):
    def __call__(
        self,
        ctx: Context,
        step: step_lib.StepSync,
    ) -> types.Serializable:
        ...


def _is_function_handler_async(
    value: FunctionHandlerAsync | FunctionHandlerSync,
) -> typing.TypeGuard[FunctionHandlerAsync]:
    return inspect.iscoroutinefunction(value)


def _is_function_handler_sync(
    value: FunctionHandlerAsync | FunctionHandlerSync,
) -> typing.TypeGuard[FunctionHandlerSync]:
    return not inspect.iscoroutinefunction(value)


class FunctionOpts(types.BaseModel):
    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    batch_events: function_config.Batch | None = None
    cancel: list[function_config.Cancel] | None = None
    concurrency: list[function_config.Concurrency] | None = None
    debounce: function_config.Debounce | None = None
    id: str
    name: str
    on_failure: FunctionHandlerAsync | FunctionHandlerSync | None = None
    rate_limit: function_config.RateLimit | None = None
    retries: int | None = None
    throttle: function_config.Throttle | None = None

    def convert_validation_error(
        self,
        err: pydantic.ValidationError,
    ) -> BaseException:
        return errors.InvalidConfigError.from_validation_error(err)


class Function:
    _handler: FunctionHandlerAsync | FunctionHandlerSync
    _on_failure_fn_id: str | None = None
    _opts: FunctionOpts
    _trigger: function_config.TriggerCron | function_config.TriggerEvent

    @property
    def id(self) -> str:
        return self._opts.id

    @property
    def is_handler_async(self) -> bool:
        """Whether the main handler is async."""
        return _is_function_handler_async(self._handler)

    @property
    def is_on_failure_handler_async(self) -> bool | None:
        """
        Whether the on_failure handler is async. Returns None if there isn't an
        on_failure handler.
        """
        if self._opts.on_failure is None:
            return None
        return _is_function_handler_async(self._opts.on_failure)

    @property
    def on_failure_fn_id(self) -> str | None:
        return self._on_failure_fn_id

    def __init__(
        self,
        opts: FunctionOpts,
        trigger: function_config.TriggerCron | function_config.TriggerEvent,
        handler: FunctionHandlerAsync | FunctionHandlerSync,
        middleware: list[
            type[middleware_lib.Middleware | middleware_lib.MiddlewareSync]
        ]
        | None = None,
    ) -> None:
        self._handler = handler
        self._middleware = middleware or []
        self._opts = opts
        self._trigger = trigger

        if opts.on_failure is not None:
            self._on_failure_fn_id = f"{opts.id}-failure"

    async def call(  # noqa: C901
        self,
        call: execution.Call,
        client: client_lib.Inngest,
        ctx: Context,
        fn_id: str,
        middleware: middleware_lib.MiddlewareManager,
        target_hashed_id: str | None,
    ) -> execution.CallResult:
        middleware = middleware_lib.MiddlewareManager.from_manager(middleware)
        for m in self._middleware:
            middleware.add(m)

        memos = step_lib.StepMemos.from_raw(call.steps)

        # Give middleware the opportunity to change some of params passed to the
        # user's handler.
        new_ctx = await middleware.transform_input(ctx)
        if isinstance(new_ctx, Exception):
            return execution.CallError.from_error(new_ctx)
        ctx = new_ctx

        # No memoized data means we're calling the function for the first time.
        if memos.size == 0:
            err = await middleware.before_execution()
            if isinstance(err, Exception):
                return execution.CallError.from_error(err)

        try:
            handler: FunctionHandlerAsync | FunctionHandlerSync
            if self.id == fn_id:
                handler = self._handler
            elif self.on_failure_fn_id == fn_id:
                if self._opts.on_failure is None:
                    return execution.CallError.from_error(
                        errors.MissingFunctionError("on_failure not defined")
                    )
                handler = self._opts.on_failure
            else:
                return execution.CallError.from_error(
                    errors.MissingFunctionError("function ID mismatch")
                )

            output: object

            try:
                # # Determine whether the handler is async (i.e. if we need to await
                # # it). Sync functions are OK in async contexts, so it's OK if the
                # # handler is sync.
                if _is_function_handler_async(handler):
                    output = await handler(
                        ctx=ctx,
                        step=step_lib.Step(
                            client,
                            memos,
                            middleware,
                            step_lib.StepIDCounter(),
                            target_hashed_id,
                        ),
                    )
                elif _is_function_handler_sync(handler):
                    output = handler(
                        ctx=ctx,
                        step=step_lib.StepSync(
                            client,
                            memos,
                            middleware,
                            step_lib.StepIDCounter(),
                            target_hashed_id,
                        ),
                    )
                else:
                    # Should be unreachable but Python's custom type guards don't
                    # support negative checks :(
                    return execution.CallError.from_error(
                        errors.UnknownError(
                            "unable to determine function handler type"
                        )
                    )
            except Exception as user_err:
                transforms.remove_first_traceback_frame(user_err)
                raise _UserError(user_err)

            err = await middleware.after_execution()
            if isinstance(err, Exception):
                return execution.CallError.from_error(err)

            output = await middleware.transform_output(
                # Function output isn't wrapped in an Output object, so we need
                # to wrap it to make it compatible with middleware.
                execution.Output(data=output)
            )
            if isinstance(output, Exception):
                return execution.CallError.from_error(output)

            if output is None:
                return execution.FunctionCallResponse(data=None)
            return execution.FunctionCallResponse(data=output.data)
        except step_lib.ResponseInterrupt as interrupt:
            err = await middleware.after_execution()
            if isinstance(err, Exception):
                return execution.CallError.from_error(err)

            # TODO: How should transform_output work with multiple responses?
            if len(interrupt.responses) == 1:
                output = await middleware.transform_output(
                    interrupt.responses[0].data
                )
                if isinstance(output, Exception):
                    return execution.CallError.from_error(output)
                interrupt.responses[0].data = output

            return interrupt.responses
        except _UserError as err:
            return execution.CallError.from_error(err.err)
        except step_lib.SkipInterrupt as err:
            # This should only happen in a non-deterministic scenario, where
            # step targeting is enabled and an unexpected step is encountered.
            # We don't currently have a way to recover from this scenario.

            return execution.CallError.from_error(
                errors.UnexpectedStepError(
                    f'found step "{err.step_id}" when targeting a different step'
                )
            )
        except Exception as err:
            return execution.CallError.from_error(err)

    def call_sync(  # noqa: C901
        self,
        call: execution.Call,
        client: client_lib.Inngest,
        ctx: Context,
        fn_id: str,
        middleware: middleware_lib.MiddlewareManager,
        target_hashed_id: str | None,
    ) -> execution.CallResult:
        middleware = middleware_lib.MiddlewareManager.from_manager(middleware)
        for m in self._middleware:
            middleware.add(m)

        memos = step_lib.StepMemos.from_raw(call.steps)

        # Give middleware the opportunity to change some of params passed to the
        # user's handler.
        new_ctx = middleware.transform_input_sync(ctx)
        if isinstance(new_ctx, Exception):
            return execution.CallError.from_error(new_ctx)
        ctx = new_ctx

        # No memoized data means we're calling the function for the first time.
        if memos.size == 0:
            middleware.before_execution_sync()

        try:
            handler: FunctionHandlerAsync | FunctionHandlerSync
            if self.id == fn_id:
                handler = self._handler
            elif self.on_failure_fn_id == fn_id:
                if self._opts.on_failure is None:
                    return execution.CallError.from_error(
                        errors.MissingFunctionError("on_failure not defined")
                    )
                handler = self._opts.on_failure
            else:
                return execution.CallError.from_error(
                    errors.MissingFunctionError("function ID mismatch")
                )

            if _is_function_handler_sync(handler):
                try:
                    output: object = handler(
                        ctx=ctx,
                        step=step_lib.StepSync(
                            client,
                            memos,
                            middleware,
                            step_lib.StepIDCounter(),
                            target_hashed_id,
                        ),
                    )
                except Exception as user_err:
                    transforms.remove_first_traceback_frame(user_err)
                    raise _UserError(user_err)
            else:
                return execution.CallError.from_error(
                    errors.MismatchedSyncError(
                        "encountered async function in non-async context"
                    )
                )

            err = middleware.after_execution_sync()
            if isinstance(err, Exception):
                return execution.CallError.from_error(err)

            output = middleware.transform_output_sync(
                # Function output isn't wrapped in an Output object, so we need
                # to wrap it to make it compatible with middleware.
                execution.Output(data=output)
            )
            if isinstance(output, Exception):
                return execution.CallError.from_error(output)

            if output is None:
                return execution.FunctionCallResponse(data=None)
            return execution.FunctionCallResponse(data=output.data)
        except step_lib.ResponseInterrupt as interrupt:
            err = middleware.after_execution_sync()
            if isinstance(err, Exception):
                return execution.CallError.from_error(err)

            # TODO: How should transform_output work with multiple responses?
            if len(interrupt.responses) == 1:
                output = middleware.transform_output_sync(
                    interrupt.responses[0].data
                )
                if isinstance(output, Exception):
                    return execution.CallError.from_error(output)
                interrupt.responses[0].data = output

            return interrupt.responses
        except _UserError as err:
            return execution.CallError.from_error(err.err)
        except step_lib.SkipInterrupt as err:
            # This should only happen in a non-deterministic scenario, where
            # step targeting is enabled and an unexpected step is encountered.
            # We don't currently have a way to recover from this scenario.

            return execution.CallError.from_error(
                errors.UnexpectedStepError(
                    f'found step "{err.step_id}" when targeting a different step'
                )
            )
        except Exception as err:
            return execution.CallError.from_error(err)

    def get_config(self, app_url: str) -> _Config:
        fn_id = self._opts.id
        name = self._opts.name

        if self._opts.retries is not None:
            retries = function_config.Retries(attempts=self._opts.retries)
        else:
            retries = None

        url = (
            app_url
            + "?"
            + urllib.parse.urlencode(
                {
                    "fnId": fn_id,
                    "stepId": const.ROOT_STEP_ID,
                }
            )
        )

        main = function_config.FunctionConfig(
            batch_events=self._opts.batch_events,
            cancel=self._opts.cancel,
            concurrency=self._opts.concurrency,
            debounce=self._opts.debounce,
            id=fn_id,
            name=name,
            rate_limit=self._opts.rate_limit,
            steps={
                const.ROOT_STEP_ID: function_config.Step(
                    id=const.ROOT_STEP_ID,
                    name=const.ROOT_STEP_ID,
                    retries=retries,
                    runtime=function_config.Runtime(
                        type="http",
                        url=url,
                    ),
                ),
            },
            throttle=self._opts.throttle,
            triggers=[self._trigger],
        )

        on_failure = None
        if self.on_failure_fn_id is not None:
            url = (
                app_url
                + "?"
                + urllib.parse.urlencode(
                    {
                        "fnId": self.on_failure_fn_id,
                        "stepId": const.ROOT_STEP_ID,
                    }
                )
            )

            on_failure = function_config.FunctionConfig(
                id=self.on_failure_fn_id,
                name=f"{name} (failure)",
                steps={
                    const.ROOT_STEP_ID: function_config.Step(
                        id=const.ROOT_STEP_ID,
                        name=const.ROOT_STEP_ID,
                        retries=function_config.Retries(attempts=0),
                        runtime=function_config.Runtime(
                            type="http",
                            url=url,
                        ),
                    )
                },
                triggers=[
                    function_config.TriggerEvent(
                        event=const.InternalEvents.FUNCTION_FAILED.value,
                        expression=f"event.data.function_id == '{self.id}'",
                    )
                ],
            )

        return _Config(main=main, on_failure=on_failure)

    def get_id(self) -> str:
        return self._opts.id


class _UserError(Exception):
    """
    Wrap an error that occurred in user code.
    """

    def __init__(self, err: Exception) -> None:
        self.err = err
