from __future__ import annotations

import dataclasses
import inspect
import typing
import urllib.parse

import pydantic

from inngest._internal import (
    client_lib,
    errors,
    execution_lib,
    middleware_lib,
    server_lib,
    types,
)


@dataclasses.dataclass
class _Config:
    # The user-defined function
    main: server_lib.FunctionConfig

    # The internal on_failure function
    on_failure: typing.Optional[server_lib.FunctionConfig]


class FunctionOpts(types.BaseModel):
    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    batch_events: typing.Optional[server_lib.Batch]
    cancel: typing.Optional[list[server_lib.Cancel]]
    concurrency: typing.Optional[list[server_lib.Concurrency]]
    debounce: typing.Optional[server_lib.Debounce]

    # Unique within an environment
    fully_qualified_id: str

    idempotency: typing.Optional[str]

    # Unique within an app
    local_id: str

    name: str
    on_failure: typing.Union[
        execution_lib.FunctionHandlerAsync[typing.Any],
        execution_lib.FunctionHandlerSync[typing.Any],
        None,
    ]
    priority: typing.Optional[server_lib.Priority]
    rate_limit: typing.Optional[server_lib.RateLimit]
    retries: typing.Optional[int]
    throttle: typing.Optional[server_lib.Throttle]
    timeouts: typing.Optional[server_lib.Timeouts]
    singleton: typing.Optional[server_lib.Singleton]

    def convert_validation_error(
        self,
        err: pydantic.ValidationError,
    ) -> BaseException:
        return errors.FunctionConfigInvalidError.from_validation_error(err)


class Function(typing.Generic[types.T]):
    _handler: typing.Union[
        execution_lib.FunctionHandlerAsync[types.T],
        execution_lib.FunctionHandlerSync[types.T],
    ]
    _on_failure_fn_id: typing.Optional[str] = None
    _opts: FunctionOpts
    _triggers: list[
        typing.Union[server_lib.TriggerCron, server_lib.TriggerEvent]
    ]

    @property
    def id(self) -> str:
        return self._opts.fully_qualified_id

    @property
    def is_handler_async(self) -> bool:
        """Whether the main handler is async."""
        return inspect.iscoroutinefunction(self._handler)

    @property
    def is_on_failure_handler_async(self) -> typing.Optional[bool]:
        """
        Whether the on_failure handler is async. Returns None if there isn't an
        on_failure handler.
        """
        if self._opts.on_failure is None:
            return None
        return inspect.iscoroutinefunction(self._opts.on_failure)

    @property
    def local_id(self) -> str:
        return self._opts.local_id

    @property
    def name(self) -> str:
        return self._opts.name

    @property
    def on_failure_fn_id(self) -> typing.Optional[str]:
        return self._on_failure_fn_id

    def __init__(
        self,
        opts: FunctionOpts,
        trigger: typing.Union[
            server_lib.TriggerCron,
            server_lib.TriggerEvent,
            list[typing.Union[server_lib.TriggerCron, server_lib.TriggerEvent]],
        ],
        handler: typing.Union[
            execution_lib.FunctionHandlerAsync[types.T],
            execution_lib.FunctionHandlerSync[types.T],
        ],
        output_type: object = object,
        middleware: typing.Optional[
            list[middleware_lib.UninitializedMiddleware]
        ] = None,
    ) -> None:
        self._handler = handler
        self._middleware = middleware or []
        self._opts = opts
        self._output_type = output_type
        self._triggers = trigger if isinstance(trigger, list) else [trigger]

        if opts.on_failure is not None:
            if (
                self.is_handler_async
                and self.is_on_failure_handler_async is False
            ):
                raise errors.Error(
                    f"an async function cannot have a non-async on_failure handler (function {opts.local_id})"
                )
            if (
                self.is_handler_async is False
                and self.is_on_failure_handler_async is True
            ):
                raise errors.Error(
                    f"a non-async function cannot have an async on_failure handler (function {opts.local_id})"
                )

            self._on_failure_fn_id = f"{opts.fully_qualified_id}-failure"

    async def call(
        self,
        client: client_lib.Inngest,
        ctx: execution_lib.Context,
        fn_id: str,
        middleware: middleware_lib.MiddlewareManager,
    ) -> execution_lib.CallResult:
        for m in self._middleware:
            middleware.add(m)

        if self.id == fn_id:
            handler = self._handler
            output_type = self._output_type
        elif self.on_failure_fn_id == fn_id:
            if self._opts.on_failure is None:
                return execution_lib.CallResult(
                    errors.FunctionNotFoundError("on_failure not defined")
                )
            handler = self._opts.on_failure

            # We only need to serialize to JSON so any type is fine.
            # Deserialization isn't necessary since on_failure handlers aren't
            # invoked via `step.invoke`.
            output_type = object
        else:
            return execution_lib.CallResult(
                errors.FunctionNotFoundError("function ID mismatch")
            )

        if not execution_lib.is_function_handler_async(handler):
            raise errors.UnreachableError("handler is not async")

        call_res = await ctx.step._execution.run(
            client,
            ctx,
            handler,
            self,
            output_type,
        )

        err = await middleware.transform_output(call_res)
        if isinstance(err, Exception):
            return execution_lib.CallResult(err)

        err = await middleware.before_response()
        if isinstance(err, Exception):
            return execution_lib.CallResult(err)

        return call_res

    def call_sync(
        self,
        client: client_lib.Inngest,
        ctx: execution_lib.ContextSync,
        fn_id: str,
        middleware: middleware_lib.MiddlewareManager,
    ) -> execution_lib.CallResult:
        for m in self._middleware:
            middleware.add(m)

        if self.id == fn_id:
            handler = self._handler
            output_type = self._output_type
        elif self.on_failure_fn_id == fn_id:
            if self._opts.on_failure is None:
                return execution_lib.CallResult(
                    errors.FunctionNotFoundError("on_failure not defined")
                )
            handler = self._opts.on_failure

            # We only need to serialize to JSON so any type is fine.
            # Deserialization isn't necessary since on_failure handlers aren't
            # invoked via `step.invoke`.
            output_type = object
        else:
            return execution_lib.CallResult(
                errors.FunctionNotFoundError("function ID mismatch")
            )

        if not execution_lib.is_function_handler_sync(handler):
            raise errors.UnreachableError("handler is not sync")

        # We don't need to pass a thread pool here because the sync handler is
        # not used by Connect.
        call_res = ctx.step._execution.run(
            client,
            ctx,
            handler,
            self,
            output_type,
        )

        err = middleware.transform_output_sync(call_res)
        if isinstance(err, Exception):
            return execution_lib.CallResult(err)

        err = middleware.before_response_sync()
        if isinstance(err, Exception):
            return execution_lib.CallResult(err)

        return call_res

    def get_config(self, app_url: str) -> _Config:
        fn_id = self._opts.fully_qualified_id
        name = self._opts.name

        if self._opts.retries is not None:
            retries = server_lib.Retries(attempts=self._opts.retries)
        else:
            retries = None

        url = (
            app_url
            + "?"
            + urllib.parse.urlencode(
                {
                    "fnId": fn_id,
                    "stepId": server_lib.ROOT_STEP_ID,
                }
            )
        )

        runtime_type: typing.Literal["http", "ws"] = "http"
        if url.startswith("wss://"):
            runtime_type = "ws"

        main = server_lib.FunctionConfig(
            batch_events=self._opts.batch_events,
            cancel=self._opts.cancel,
            concurrency=self._opts.concurrency,
            debounce=self._opts.debounce,
            id=fn_id,
            idempotency=self._opts.idempotency,
            name=name,
            priority=self._opts.priority,
            rate_limit=self._opts.rate_limit,
            steps={
                server_lib.ROOT_STEP_ID: server_lib.Step(
                    id=server_lib.ROOT_STEP_ID,
                    name=server_lib.ROOT_STEP_ID,
                    retries=retries,
                    runtime=server_lib.Runtime(
                        type=runtime_type,
                        url=url,
                    ),
                ),
            },
            throttle=self._opts.throttle,
            timeouts=self._opts.timeouts,
            triggers=self._triggers,
            singleton=self._opts.singleton,
        )

        on_failure = None
        if self.on_failure_fn_id is not None:
            url = (
                app_url
                + "?"
                + urllib.parse.urlencode(
                    {
                        "fnId": self.on_failure_fn_id,
                        "stepId": server_lib.ROOT_STEP_ID,
                    }
                )
            )

            on_failure = server_lib.FunctionConfig(
                batch_events=None,
                cancel=None,
                concurrency=None,
                debounce=None,
                id=self.on_failure_fn_id,
                idempotency=None,
                name=f"{name} (failure)",
                priority=None,
                rate_limit=None,
                steps={
                    server_lib.ROOT_STEP_ID: server_lib.Step(
                        id=server_lib.ROOT_STEP_ID,
                        name=server_lib.ROOT_STEP_ID,
                        retries=server_lib.Retries(attempts=0),
                        runtime=server_lib.Runtime(
                            type="http",
                            url=url,
                        ),
                    )
                },
                throttle=None,
                timeouts=None,
                triggers=[
                    server_lib.TriggerEvent(
                        event=server_lib.InternalEvents.FUNCTION_FAILED.value,
                        expression=f"event.data.function_id == '{self.id}'",
                    )
                ],
                singleton=None,
            )

        return _Config(main=main, on_failure=on_failure)

    def get_id(self) -> str:
        return self._opts.fully_qualified_id
