"""
Users can catch StepError and raise a new error.
"""

import json
import unittest.mock

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class MyError(Exception):
    pass


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = base.BaseState()

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id

        def foo() -> None:
            raise ValueError("foo")

        try:
            ctx.step.run("foo", foo)
        except inngest.StepError:
            raise MyError("I am new")

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id

        async def foo() -> None:
            raise ValueError("foo")

        try:
            await ctx.step.run("foo", foo)
        except inngest.StepError:
            raise MyError("I am new")

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.FAILED,
        )

        assert run.output is not None
        output = json.loads(run.output)
        assert output == {
            "code": "unknown",
            "message": "I am new",
            "name": "MyError",
            "stack": unittest.mock.ANY,
        }

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
