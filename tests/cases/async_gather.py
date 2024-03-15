"""
We don't support `async.gather` yet. This test demonstrates the bug that happens
when using `async.gather`: a step is executed twice
"""

import asyncio

import inngest
import tests.helper

from . import base

_TEST_NAME = "async_gather"


class _State(base.BaseState):
    step_1a_counter = 0
    step_1b_counter = 0


def create(
    client: inngest.Inngest,
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        # This test is not applicable for sync functions
        pass

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

        def _step_1a() -> int:
            state.step_1a_counter += 1
            return 1

        def _step_1b() -> int:
            state.step_1b_counter += 1
            return 2

        await asyncio.gather(
            step.run("1a", _step_1a),
            step.run("1b", _step_1b),
        )

    def run_test(self: base.TestClass) -> None:
        if is_sync:
            # This test is not applicable for sync functions
            return

        self.client.send_sync(inngest.Event(name=event_name))
        tests.helper.client.wait_for_run_status(
            state.wait_for_run_id(),
            tests.helper.RunStatus.COMPLETED,
        )

        assert state.step_1a_counter + state.step_1b_counter == 3

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
