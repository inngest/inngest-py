import datetime
import json

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    step_1a_counter = 0
    step_1b_counter = 0
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

        state.parallel_output = ctx.group.parallel(
            (lambda: step.run("a", lambda: None),)  # type: ignore
        )

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

        state.parallel_output = await ctx.group.parallel(
            (lambda: step.run("a", lambda: None),)
        )

        async def _step_after() -> None:
            state.step_after_counter += 1

        await step.run("after", _step_after)

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))

        run = test_core.helper.client.wait_for_run_status(
            state.wait_for_run_id(),
            test_core.helper.RunStatus.FAILED,
        )

        assert run.output is not None
        output = json.loads(run.output)

        if is_sync:
            assert (
                output["message"]
                == "group.parallel can only be called in an async Inngest function"
            )
        else:
            assert (
                output["message"]
                == "group.parallel_sync can only be called in a non-async Inngest function"
            )

    if is_sync:
        fn = [fn_sync, fn_child_sync]
    else:
        fn = [fn_async, fn_child_async]

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
