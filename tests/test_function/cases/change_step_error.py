"""
Users can catch StepError and raise a new error.
"""

import json
import unittest.mock

import inngest
import tests.helper
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
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.run_id = ctx.run_id

        def foo() -> None:
            raise ValueError("foo")

        try:
            step.run("foo", foo)
        except inngest.StepError:
            raise MyError("I am new")

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_id = ctx.run_id

        def foo() -> None:
            raise ValueError("foo")

        try:
            await step.run("foo", foo)
        except inngest.StepError:
            raise MyError("I am new")

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        run = tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.FAILED,
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
