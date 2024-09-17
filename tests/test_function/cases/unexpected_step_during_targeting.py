"""
Test scenario when an unexpected step is encountered when another step is
targeted. This can happen when a function is non-deterministic, where a new step
appears when a parallel step is targeted.
"""

import json

import inngest
import tests.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    request_counter = 0
    step_parallel_1_counter = 0
    step_parallel_2_counter = 0
    step_unexpected_counter = 0


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

        def parallel_1() -> None:
            state.step_parallel_1_counter += 1

        def parallel_2() -> None:
            state.step_parallel_2_counter += 1

        def unexpected() -> None:
            state.step_unexpected_counter += 1

        is_targeting_enabled = step._target_hashed_id is not None
        if is_targeting_enabled:
            step.run("unexpected", unexpected)

        ctx.group.parallel_sync(
            (
                lambda: step.run("parallel_1", parallel_1),
                lambda: step.run("parallel_2", parallel_2),
            )
        )

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

        async def parallel_1() -> None:
            state.step_parallel_1_counter += 1

        async def parallel_2() -> None:
            state.step_parallel_2_counter += 1

        async def unexpected() -> None:
            state.step_unexpected_counter += 1

        is_targeting_enabled = step._target_hashed_id is not None
        if is_targeting_enabled:
            await step.run("unexpected", unexpected)

        await ctx.group.parallel(
            (
                lambda: step.run("parallel_1", parallel_1),
                lambda: step.run("parallel_2", parallel_2),
            )
        )

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
            "code": "step_unexpected",
            "message": 'found step "unexpected" when targeting a different step',
            "name": "StepUnexpectedError",
            "stack": None,
        }

        # None of the step callbacks were called
        assert state.step_parallel_1_counter == 0
        assert state.step_parallel_2_counter == 0
        assert state.step_unexpected_counter == 0

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
