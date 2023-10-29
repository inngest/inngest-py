from __future__ import annotations

import hashlib
import json
import traceback
import typing

from inngest._internal import (
    client_lib,
    errors,
    event_lib,
    execution,
    function_config,
    step_lib,
)

from . import base


@typing.runtime_checkable
class _FunctionHandler(typing.Protocol):
    def __call__(
        self,
        *,
        attempt: int,
        event: event_lib.Event,
        events: list[event_lib.Event],
        run_id: str,
        step: step_lib.Step,
    ) -> typing.Awaitable[object]:
        ...


class FunctionOpts(base.FunctionOptsBase[_FunctionHandler]):
    pass


def create_function(
    *,
    batch_events: function_config.Batch | None = None,
    cancel: list[function_config.Cancel] | None = None,
    debounce: function_config.Debounce | None = None,
    fn_id: str,
    name: str | None = None,
    on_failure: _FunctionHandler | None = None,
    rate_limit: function_config.RateLimit | None = None,
    retries: int | None = None,
    throttle: function_config.Throttle | None = None,
    trigger: function_config.TriggerCron | function_config.TriggerEvent,
) -> typing.Callable[[_FunctionHandler], Function]:
    def decorator(func: _FunctionHandler) -> Function:
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
        )

    return decorator


class Function(base.FunctionBase):
    def __init__(
        self,
        opts: FunctionOpts,
        trigger: function_config.TriggerCron | function_config.TriggerEvent,
        handler: _FunctionHandler,
    ) -> None:
        self._handler = handler
        self._opts = opts
        self._trigger = trigger

        if opts.on_failure is not None:
            # Create a random suffix to avoid collisions with the main
            # function's ID.
            suffix = hashlib.sha1(opts.id.encode("utf-8")).hexdigest()[:8]

            self._on_failure_fn_id = f"{opts.id}-{suffix}"

    async def call(
        self,
        call: execution.Call,
        client: client_lib.Inngest,
        fn_id: str,
    ) -> list[execution.CallResponse] | str | execution.CallError:
        try:
            handler: _FunctionHandler

            if self.id == fn_id:
                handler = self._handler
            elif self.on_failure_fn_id == fn_id:
                if self._opts.on_failure is None:
                    raise errors.MissingFunction("on_failure not defined")
                handler = self._opts.on_failure
            else:
                raise errors.MissingFunction("function ID mismatch")

            res = await handler(
                attempt=call.ctx.attempt,
                event=call.event,
                events=call.events,
                run_id=call.ctx.run_id,
                step=step_lib.Step(
                    client,
                    call.steps,
                    step_lib.StepIDCounter(),
                ),
            )

            return json.dumps(res)
        except step_lib.Interrupt as out:
            return [
                execution.CallResponse(
                    data=out.data,
                    display_name=out.display_name,
                    id=out.hashed_id,
                    name=out.name,
                    op=out.op,
                    opts=out.opts,
                )
            ]
        except Exception as err:
            is_retriable = isinstance(err, errors.NonRetriableError) is False

            return execution.CallError(
                is_retriable=is_retriable,
                message=str(err),
                name=type(err).__name__,
                stack=traceback.format_exc(),
            )
