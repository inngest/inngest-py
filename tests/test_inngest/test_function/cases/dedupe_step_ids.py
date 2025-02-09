"""
Test support for duplicate step IDs. Executor expects unique step IDs, so SDK
adds an implicit counter to the end of the user-specified step ID. The most
common use case for duplicate step IDs is in loops.
"""

import json

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    step_1_counter = 0
    step_1_output: object = None
    step_2_counter = 0
    step_2_output: object = None


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

        for i in range(2):

            def step_fn() -> int:
                if i == 0:
                    state.step_1_counter += 1
                elif i == 1:
                    state.step_2_counter += 1
                else:
                    raise Exception(f"unexpected i: {i}")

                return i

            output = step.run("foo", step_fn)
            if i == 0:
                state.step_1_output = output
            elif i == 1:
                state.step_2_output = output
            else:
                raise Exception(f"unexpected i: {i}")

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

        for i in range(2):

            async def step_fn() -> int:
                if i == 0:
                    state.step_1_counter += 1
                elif i == 1:
                    state.step_2_counter += 1
                else:
                    raise Exception(f"unexpected i: {i}")

                return i

            output = await step.run("foo", step_fn)
            if i == 0:
                state.step_1_output = output
            elif i == 1:
                state.step_2_output = output
            else:
                raise Exception(f"unexpected i: {i}")

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        assert state.step_1_counter == 1
        assert state.step_1_output == 0
        step_1_output_in_api = json.loads(
            test_core.helper.client.get_step_output(
                run_id=run_id,
                step_id="foo",
            )
        )
        assert step_1_output_in_api == {"data": 0}

        assert state.step_2_counter == 1
        assert state.step_2_output == 1
        step_2_output_in_api = json.loads(
            test_core.helper.client.get_step_output(
                run_id=run_id,
                step_id="foo:1",
            )
        )
        assert step_2_output_in_api == {"data": 1}

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
