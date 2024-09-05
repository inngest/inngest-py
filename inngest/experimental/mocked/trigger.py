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
    server_lib,
    step_lib,
)

from .client import Inngest
from .consts import Status, Timeout
from .errors import UnstubbedStepError


def trigger(
    fn: inngest.Function,
    event: typing.Union[inngest.Event, list[inngest.Event]],
    client: Inngest,
    *,
    step_stubs: typing.Optional[dict[str, object]] = None,
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

    stack: list[str] = []
    steps: dict[str, object] = {}
    planned = set[str]()

    while True:
        step_id: typing.Optional[str] = None
        if len(planned) > 0:
            step_id = planned.pop()

        logger = unittest.mock.Mock()
        request = server_lib.ServerRequest(
            ctx=server_lib.ServerRequestCtx(
                attempt=0,
                disable_immediate_execution=True,
                run_id="abc123",
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
        )

        ctx = execution_lib.Context(
            attempt=request.ctx.attempt,
            event=event[0],
            events=event,
            logger=logger,
            run_id=request.ctx.run_id,
        )

        memos = step_lib.StepMemos.from_raw(steps)

        if fn.is_handler_async:
            loop = async_lib.get_event_loop()
            if loop is None:
                loop = asyncio.new_event_loop()

            res = loop.run_until_complete(
                fn.call(
                    client,
                    ctx,
                    fn.id,
                    middleware,
                    request,
                    memos,
                    step_id,
                )
            )
        else:
            res = fn.call_sync(
                client,
                ctx,
                fn.id,
                middleware,
                request,
                memos,
                step_id,
            )

        if res.error:
            return _Result(
                error=res.error,
                output=None,
                status=Status.FAILED,
            )

        if res.multi:
            for step in res.multi:
                if not step.step:
                    # Unreachable
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
    error: typing.Optional[Exception]
    output: object
    status: Status
