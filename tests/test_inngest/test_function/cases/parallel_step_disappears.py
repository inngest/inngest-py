"""
If a parallel step disappears by the time it's "targeted", the run fails.
"""

import datetime
import json
import typing

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    request_counter = 0
    step_1a_counter = 0
    step_1b_counter = 0
    step_1c_counter = 0
    step_after_counter = 0
    parallel_output: object = None


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    @client.create_function(
        fn_id=f"{fn_id}/child",
        retries=0,
        trigger=inngest.TriggerEvent(event="never"),
    )
    def fn_child_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> str:
        step.sleep("sleep", datetime.timedelta(seconds=1))
        return "done"

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
        state.request_counter += 1

        steps: tuple[typing.Any, ...] = (
            lambda: step.run("1a", lambda: None),
            lambda: step.run("1b", lambda: None),
        )

        if state.request_counter == 1:
            steps += (lambda: step.run("1c", lambda: None),)

        ctx.group.parallel_sync(steps)
        step.run("after", lambda: None)

    @client.create_function(
        fn_id=f"{fn_id}/child",
        retries=0,
        trigger=inngest.TriggerEvent(event="never"),
    )
    async def fn_child_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> str:
        await step.sleep("sleep", datetime.timedelta(seconds=1))
        return "done"

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
        state.request_counter += 1

        steps: tuple[typing.Any, ...] = (
            lambda: step.run("1a", lambda: None),
            lambda: step.run("1b", lambda: None),
        )

        if state.request_counter == 1:
            steps += (lambda: step.run("1c", lambda: None),)

        await ctx.group.parallel(steps)
        await step.run("after", lambda: None)

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))

        run_id = state.wait_for_run_id()
        run = test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.FAILED,
        )
        assert run.output is not None
        output = json.loads(run.output)
        assert output == {
            "code": "step_unexpected",
            "message": 'found step "after" when targeting a different step',
            "name": "StepUnexpectedError",
            "stack": None,
        }, run.output

    if is_sync:
        fn = [fn_sync, fn_child_sync]
    else:
        fn = [fn_async, fn_child_async]

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
