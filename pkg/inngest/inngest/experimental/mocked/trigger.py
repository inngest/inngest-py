from __future__ import annotations

import asyncio
import dataclasses
import typing
import unittest.mock

import inngest
from inngest._internal import (
    async_lib,
    execution_lib,
    middleware_lib,
    net,
    server_lib,
    step_lib,
)

from .client import Inngest
from .consts import Status, Timeout
from .errors import UnstubbedStepError


def trigger(
    fn: inngest.Function[typing.Any],
    event: inngest.Event | list[inngest.Event],
    client: Inngest,
    *,
    step_stubs: dict[str, object] | None = None,
) -> _Result:
    """
    Trigger a function.

    Args:
    ----
        fn: Function to trigger.
        event: Triggering event.
        client: Mock Inngest client.
        step_stubs: Static step stubs. Keys are step IDs and values are stubs.
    """

    if not isinstance(event, list):
        event = [event]
    elif len(event) == 0:
        raise Exception("Must provide at least 1 event")

    if step_stubs is None:
        step_stubs = {}

    timings = net.ServerTimings()
    stack: list[str] = []
    steps: dict[str, object] = {}
    planned = set[str]()
    attempt = 0

    max_attempt = 4
    if fn._opts.retries is not None:
        max_attempt = fn._opts.retries

    while True:
        step_id: str | None = None
        if len(planned) > 0:
            step_id = planned.pop()

        logger = unittest.mock.Mock()
        request = server_lib.ServerRequest(
            ctx=server_lib.ServerRequestCtx(
                attempt=attempt,
                disable_immediate_execution=True,
                run_id="test",
                stack=server_lib.ServerRequestCtxStack(stack=stack),
            ),
            event=event[0],
            events=event,
            steps=steps,
            use_api=False,
        )
        middleware = middleware_lib.MiddlewareManager.from_client(
            client,
            {},
            timings,
        )

        memos = step_lib.StepMemos.from_raw(steps)

        ctx: execution_lib.Context | execution_lib.ContextSync
        if fn.is_handler_async:
            ctx = execution_lib.Context(
                attempt=request.ctx.attempt,
                event=event[0],
                events=event,
                group=step_lib.Group(),
                logger=logger,
                run_id=request.ctx.run_id,
                step=step_lib.Step(
                    client,
                    execution_lib.ExecutionV0(
                        memos,
                        middleware,
                        request,
                        step_id,
                        timings,
                    ),
                    middleware,
                    step_lib.StepIDCounter(),
                    step_id,
                ),
            )

            loop = async_lib.get_event_loop()
            if loop is None:
                loop = asyncio.new_event_loop()

            res = loop.run_until_complete(
                fn.call(
                    client,
                    ctx,
                    fn.id,
                    middleware,
                )
            )
        else:
            ctx = execution_lib.ContextSync(
                attempt=request.ctx.attempt,
                event=event[0],
                events=event,
                group=step_lib.GroupSync(),
                logger=logger,
                run_id=request.ctx.run_id,
                step=step_lib.StepSync(
                    client,
                    execution_lib.ExecutionV0Sync(
                        memos,
                        middleware,
                        request,
                        step_id,
                        timings,
                    ),
                    middleware,
                    step_lib.StepIDCounter(),
                    step_id,
                ),
            )

            res = fn.call_sync(
                client,
                ctx,
                fn.id,
                middleware,
            )

        if res.error:
            if attempt >= max_attempt:
                return _Result(
                    error=res.error,
                    output=None,
                    status=Status.FAILED,
                )

            attempt += 1
            continue

        if res.multi:
            for step in res.multi:
                if not step.step:
                    # Unreachable
                    continue

                if step.error:
                    if attempt >= max_attempt:
                        return _Result(
                            error=step.error,
                            output=None,
                            status=Status.FAILED,
                        )

                    attempt += 1
                    continue

                if step.step.display_name in step_stubs:
                    stub = step_stubs[step.step.display_name]
                    if stub is Timeout:
                        stub = None

                    steps[step.step.id] = stub
                    stack.append(step.step.id)
                    continue

                if step.step.op is server_lib.Opcode.PLANNED:
                    planned.add(step.step.id)
                elif step.step.op is server_lib.Opcode.SLEEP:
                    steps[step.step.id] = None
                    stack.append(step.step.id)
                elif step.step.op is server_lib.Opcode.STEP_RUN:
                    steps[step.step.id] = step.output
                    stack.append(step.step.id)
                else:
                    raise UnstubbedStepError(step.step.display_name)

            continue

        return _Result(
            error=None,
            output=res.output,
            status=Status.COMPLETED,
        )


@dataclasses.dataclass
class _Result:
    error: Exception | None
    output: object
    status: Status
