"""
This test changes the order of steps between requests. Step order should not
break execution.
"""

import json
import typing

import inngest
import tests.helper
from inngest._internal import const

from . import base

_TEST_NAME = "inconsistent_step_order"


class _State(base.BaseState):
    request_counter = 0
    step_1_counter = 0
    step_2_counter = 0


def create(
    client: inngest.Inngest,
    framework: const.Framework,
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
        state.run_id = ctx.run_id
        state.request_counter += 1

        def step_1() -> int:
            state.step_1_counter += 1
            return 1

        def step_2() -> int:
            state.step_2_counter += 1
            return 2

        steps: list[typing.Callable[[], int]] = [
            lambda: step.run("step_1", step_1),
            lambda: step.run("step_2", step_2),
        ]

        if state.request_counter % 2 == 0:
            steps.reverse()

        steps.pop()()
        steps.pop()()

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

        async def step_1() -> int:
            state.step_1_counter += 1
            return 1

        async def step_2() -> int:
            state.step_2_counter += 1
            return 2

        steps: list[typing.Callable[[], typing.Awaitable[int]]] = [
            lambda: step.run("step_1", step_1),
            lambda: step.run("step_2", step_2),
        ]

        if state.request_counter % 2 == 0:
            steps.reverse()

        await steps.pop()()
        await steps.pop()()

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        assert state.step_1_counter == 1
        assert state.step_2_counter == 1

        step_1_output = json.loads(
            tests.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_1",
            )
        )
        assert step_1_output == {"data": 1}

        step_2_output = json.loads(
            tests.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_2",
            )
        )
        assert step_2_output == {"data": 2}

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
