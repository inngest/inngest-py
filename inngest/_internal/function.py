from __future__ import annotations

import dataclasses
import hashlib
import inspect
import typing

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
class _Config:
    # The user-defined function
    main: function_config.FunctionConfig

    # The internal on_failure function
    on_failure: function_config.FunctionConfig | None


@typing.runtime_checkable
class FunctionHandlerAsync(typing.Protocol):
    def __call__(
        self,
        *,
        attempt: int,
        event: event_lib.Event,
        events: list[event_lib.Event],
        logger: types.Logger,
        run_id: str,
        step: step_lib.Step,
    ) -> typing.Awaitable[types.Serializable]:
        ...


@typing.runtime_checkable
class FunctionHandlerSync(typing.Protocol):
    def __call__(
        self,
        *,
        attempt: int,
        event: event_lib.Event,
        events: list[event_lib.Event],
        logger: types.Logger,
        run_id: str,
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
    debounce: function_config.Debounce | None = None
    id: str
    name: str | None = None
    on_failure: FunctionHandlerAsync | FunctionHandlerSync | None = None
    rate_limit: function_config.RateLimit | None = None
    retries: int | None = None
    throttle: function_config.Throttle | None = None

    def convert_validation_error(
        self,
        err: pydantic.ValidationError,
    ) -> BaseException:
        return errors.InvalidConfig.from_validation_error(err)


def create_function(
    *,
    batch_events: function_config.Batch | None = None,
    cancel: list[function_config.Cancel] | None = None,
    debounce: function_config.Debounce | None = None,
    fn_id: str,
    middleware: list[
        type[middleware_lib.Middleware | middleware_lib.MiddlewareSync]
    ]
    | None = None,
    name: str | None = None,
    on_failure: FunctionHandlerAsync | FunctionHandlerSync | None = None,
    rate_limit: function_config.RateLimit | None = None,
    retries: int | None = None,
    throttle: function_config.Throttle | None = None,
    trigger: function_config.TriggerCron | function_config.TriggerEvent,
) -> typing.Callable[[FunctionHandlerAsync | FunctionHandlerSync], Function]:
    """
    Create an Inngest function.

    Args:
    ----
        batch_events: Event batching config.
        cancel: Run cancellation config.
        debounce: Debouncing config.
        fn_id: Function ID. Changing this ID will make Inngest think this is a
            new function.
        middleware: Middleware to apply to this function.
        name: Human-readable function name. (Defaults to the function ID).
        on_failure: Function to call when this function fails.
        rate_limit: Rate limiting config.
        retries: Number of times to retry this function.
        throttle: Throttling config.
        trigger: What should trigger runs of this function.
    """

    def decorator(func: FunctionHandlerAsync | FunctionHandlerSync) -> Function:
        return Function(
            FunctionOpts(
                batch_events=batch_events,
                cancel=cancel,
                debounce=debounce,
                id=fn_id,
                name=name,
                on_failure=on_failure,
                rate_limit=rate_limit,
                retries=retries,
                throttle=throttle,
            ),
            trigger,
            func,
            middleware,
        )

    return decorator


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
            # Create a random suffix to avoid collisions with the main
            # function's ID.
            suffix = hashlib.sha1(opts.id.encode("utf-8")).hexdigest()[:8]

            self._on_failure_fn_id = f"{opts.id}-{suffix}"

    async def call(  # noqa: C901
        self,
        call: execution.Call,
        client: client_lib.Inngest,
        fn_id: str,
        call_input: execution.TransformableCallInput,
        middleware: middleware_lib.MiddlewareManager,
    ) -> execution.CallResult:
        middleware = middleware_lib.MiddlewareManager.from_manager(middleware)
        for m in self._middleware:
            middleware.add(m)

        memos = step_lib.StepMemos(call.steps)

        # Give middleware the opportunity to change some of params passed to the
        # user's handler.
        transformed_input = await middleware.transform_input(
            execution.TransformableCallInput(logger=client.logger),
        )
        if isinstance(transformed_input, Exception):
            return execution.CallError.from_error(transformed_input)
        call_input = transformed_input

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
                        errors.MissingFunction("on_failure not defined")
                    )
                handler = self._opts.on_failure
            else:
                return execution.CallError.from_error(
                    errors.MissingFunction("function ID mismatch")
                )

            output: object

            # # Determine whether the handler is async (i.e. if we need to await
            # # it). Sync functions are OK in async contexts, so it's OK if the
            # # handler is sync.
            if _is_function_handler_async(handler):
                output = await handler(
                    attempt=call.ctx.attempt,
                    event=call.event,
                    events=call.events,
                    logger=call_input.logger,
                    run_id=call.ctx.run_id,
                    step=step_lib.Step(
                        client,
                        memos,
                        middleware,
                        step_lib.StepIDCounter(),
                    ),
                )
            elif _is_function_handler_sync(handler):
                output = handler(
                    attempt=call.ctx.attempt,
                    event=call.event,
                    events=call.events,
                    logger=call_input.logger,
                    run_id=call.ctx.run_id,
                    step=step_lib.StepSync(
                        client,
                        memos,
                        middleware,
                        step_lib.StepIDCounter(),
                    ),
                )
            else:
                # Should be unreachable.
                return execution.CallError.from_error(
                    errors.UnknownError(
                        "unable to determine function handler type"
                    )
                )

            err = await middleware.after_execution()
            if isinstance(err, Exception):
                return execution.CallError.from_error(err)

            transformed_output = await middleware.transform_output(output)
            if isinstance(transformed_output, Exception):
                return execution.CallError.from_error(transformed_output)
            output = transformed_output

            return execution.FunctionCallResponse(data=output)
        except step_lib.Interrupt as interrupt:
            err = await middleware.after_execution()
            if isinstance(err, Exception):
                return execution.CallError.from_error(err)

            output = await middleware.transform_output(interrupt.data)
            if isinstance(output, Exception):
                return execution.CallError.from_error(output)

            return [
                execution.StepCallResponse(
                    data=output,
                    display_name=interrupt.display_name,
                    id=interrupt.hashed_id,
                    name=interrupt.name,
                    op=interrupt.op,
                    opts=interrupt.opts,
                )
            ]
        except Exception as err:
            return execution.CallError.from_error(err)

    def call_sync(  # noqa: C901
        self,
        call: execution.Call,
        client: client_lib.Inngest,
        fn_id: str,
        call_input: execution.TransformableCallInput,
        middleware: middleware_lib.MiddlewareManager,
    ) -> execution.CallResult:
        middleware = middleware_lib.MiddlewareManager.from_manager(middleware)
        for m in self._middleware:
            middleware.add(m)

        memos = step_lib.StepMemos(call.steps)

        # Give middleware the opportunity to change some of params passed to the
        # user's handler.
        transformed = middleware.transform_input_sync(call_input)
        if isinstance(transformed, Exception):
            return execution.CallError.from_error(transformed)
        call_input = transformed

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
                        errors.MissingFunction("on_failure not defined")
                    )
                handler = self._opts.on_failure
            else:
                return execution.CallError.from_error(
                    errors.MissingFunction("function ID mismatch")
                )

            if _is_function_handler_sync(handler):
                output: object = handler(
                    attempt=call.ctx.attempt,
                    event=call.event,
                    events=call.events,
                    logger=call_input.logger,
                    run_id=call.ctx.run_id,
                    step=step_lib.StepSync(
                        client,
                        memos,
                        middleware,
                        step_lib.StepIDCounter(),
                    ),
                )
            else:
                return execution.CallError.from_error(
                    errors.MismatchedSync(
                        "encountered async function in non-async context"
                    )
                )

            err = middleware.after_execution_sync()
            if isinstance(err, Exception):
                return execution.CallError.from_error(err)

            output = middleware.transform_output_sync(output)
            if isinstance(output, Exception):
                return execution.CallError.from_error(output)

            output_str = transforms.dump_json(output)
            if isinstance(output_str, Exception):
                return execution.CallError.from_error(output_str)

            return execution.FunctionCallResponse(data=output_str)
        except step_lib.Interrupt as interrupt:
            err = middleware.after_execution_sync()
            if isinstance(err, Exception):
                return execution.CallError.from_error(err)

            output = middleware.transform_output_sync(interrupt.data)
            if isinstance(output, Exception):
                return execution.CallError.from_error(output)

            return [
                execution.StepCallResponse(
                    data=output,
                    display_name=interrupt.display_name,
                    id=interrupt.hashed_id,
                    name=interrupt.name,
                    op=interrupt.op,
                    opts=interrupt.opts,
                )
            ]
        except Exception as err:
            return execution.CallError.from_error(err)

    def get_config(self, app_url: str) -> _Config:
        fn_id = self._opts.id

        name = fn_id
        if self._opts.name is not None:
            name = self._opts.name

        if self._opts.retries is not None:
            retries = function_config.Retries(attempts=self._opts.retries)
        else:
            retries = None

        main = function_config.FunctionConfig(
            batch_events=self._opts.batch_events,
            cancel=self._opts.cancel,
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
                        url=f"{app_url}?fnId={fn_id}&stepId={const.ROOT_STEP_ID}",
                    ),
                ),
            },
            throttle=self._opts.throttle,
            triggers=[self._trigger],
        )

        on_failure = None
        if self.on_failure_fn_id is not None:
            on_failure = function_config.FunctionConfig(
                id=self.on_failure_fn_id,
                name=f"{name} (on_failure handler)",
                steps={
                    const.ROOT_STEP_ID: function_config.Step(
                        id=const.ROOT_STEP_ID,
                        name=const.ROOT_STEP_ID,
                        retries=function_config.Retries(attempts=0),
                        runtime=function_config.Runtime(
                            type="http",
                            url=f"{app_url}?fnId={self.on_failure_fn_id}&stepId={const.ROOT_STEP_ID}",
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
