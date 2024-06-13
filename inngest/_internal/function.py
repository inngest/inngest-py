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
    execution,
    function_config,
    middleware_lib,
    orchestrator,
    step_lib,
    types,
)


@dataclasses.dataclass
class _Config:
    # The user-defined function
    main: function_config.FunctionConfig

    # The internal on_failure function
    on_failure: typing.Optional[function_config.FunctionConfig]


class FunctionOpts(types.BaseModel):
    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    batch_events: typing.Optional[function_config.Batch] = None
    cancel: typing.Optional[list[function_config.Cancel]] = None
    concurrency: typing.Optional[list[function_config.Concurrency]] = None
    debounce: typing.Optional[function_config.Debounce] = None

    # Unique within an environment
    fully_qualified_id: str

    # Unique within an app
    local_id: str

    name: str
    on_failure: typing.Union[
        execution.FunctionHandlerAsync, execution.FunctionHandlerSync, None
    ] = None
    priority: typing.Optional[function_config.Priority] = None
    rate_limit: typing.Optional[function_config.RateLimit] = None
    retries: typing.Optional[int] = None
    throttle: typing.Optional[function_config.Throttle] = None

    def convert_validation_error(
        self,
        err: pydantic.ValidationError,
    ) -> BaseException:
        return errors.FunctionConfigInvalidError.from_validation_error(err)


class Function:
    _handler: typing.Union[
        execution.FunctionHandlerAsync, execution.FunctionHandlerSync
    ]
    _on_failure_fn_id: typing.Optional[str] = None
    _opts: FunctionOpts
    _triggers: list[
        typing.Union[function_config.TriggerCron, function_config.TriggerEvent]
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
            function_config.TriggerCron,
            function_config.TriggerEvent,
            list[
                typing.Union[
                    function_config.TriggerCron, function_config.TriggerEvent
                ]
            ],
        ],
        handler: typing.Union[
            execution.FunctionHandlerAsync, execution.FunctionHandlerSync
        ],
        middleware: typing.Optional[
            list[middleware_lib.UninitializedMiddleware]
        ] = None,
    ) -> None:
        self._handler = handler
        self._middleware = middleware or []
        self._opts = opts
        self._triggers = trigger if isinstance(trigger, list) else [trigger]

        if opts.on_failure is not None:
            self._on_failure_fn_id = f"{opts.fully_qualified_id}-failure"

    async def call(
        self,
        call_context: execution.CallContext,
        client: client_lib.Inngest,
        ctx: execution.Context,
        fn_id: str,
        middleware: middleware_lib.MiddlewareManager,
        steps: step_lib.StepMemos,
        target_hashed_id: typing.Optional[str],
    ) -> execution.CallResult:
        middleware = middleware_lib.MiddlewareManager.from_manager(middleware)
        for m in self._middleware:
            middleware.add(m)

        handler: typing.Union[
            execution.FunctionHandlerAsync, execution.FunctionHandlerSync
        ]
        if self.id == fn_id:
            handler = self._handler
        elif self.on_failure_fn_id == fn_id:
            if self._opts.on_failure is None:
                return execution.CallResult(
                    errors.FunctionNotFoundError("on_failure not defined")
                )
            handler = self._opts.on_failure
        else:
            return execution.CallResult(
                errors.FunctionNotFoundError("function ID mismatch")
            )

        orc = orchestrator.OrchestratorV0(
            steps,
            middleware,
            target_hashed_id,
        )

        call_res = await orc.run(
            client,
            ctx,
            handler,
            self,
        )

        err = await middleware.transform_output(call_res)
        if isinstance(err, Exception):
            return execution.CallResult(err)

        err = await middleware.before_response()
        if isinstance(err, Exception):
            return execution.CallResult(err)

        return call_res

    def call_sync(
        self,
        client: client_lib.Inngest,
        ctx: execution.Context,
        fn_id: str,
        middleware: middleware_lib.MiddlewareManager,
        steps: step_lib.StepMemos,
        target_hashed_id: typing.Optional[str],
    ) -> execution.CallResult:
        middleware = middleware_lib.MiddlewareManager.from_manager(middleware)
        for m in self._middleware:
            middleware.add(m)

        handler: typing.Union[
            execution.FunctionHandlerAsync, execution.FunctionHandlerSync
        ]
        if self.id == fn_id:
            handler = self._handler
        elif self.on_failure_fn_id == fn_id:
            if self._opts.on_failure is None:
                return execution.CallResult(
                    errors.FunctionNotFoundError("on_failure not defined")
                )
            handler = self._opts.on_failure
        else:
            return execution.CallResult(
                errors.FunctionNotFoundError("function ID mismatch")
            )

        call_res = orchestrator.OrchestratorV0Sync(
            steps,
            middleware,
            target_hashed_id,
        ).run(
            client,
            ctx,
            handler,
            self,
        )

        err = middleware.transform_output_sync(call_res)
        if isinstance(err, Exception):
            return execution.CallResult(err)

        err = middleware.before_response_sync()
        if isinstance(err, Exception):
            return execution.CallResult(err)

        return call_res

    def get_config(self, app_url: str) -> _Config:
        fn_id = self._opts.fully_qualified_id
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
            priority=self._opts.priority,
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
            triggers=self._triggers,
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
                batch_events=None,
                cancel=None,
                concurrency=None,
                debounce=None,
                id=self.on_failure_fn_id,
                name=f"{name} (failure)",
                priority=None,
                rate_limit=None,
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
                throttle=None,
                triggers=[
                    function_config.TriggerEvent(
                        event=const.InternalEvents.FUNCTION_FAILED.value,
                        expression=f"event.data.function_id == '{self.id}'",
                    )
                ],
            )

        return _Config(main=main, on_failure=on_failure)

    def get_id(self) -> str:
        return self._opts.fully_qualified_id
