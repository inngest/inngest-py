"""
Test a parallel group of sequential steps. In other words, each parallel group
can have an arbitrary number of sequential steps.
"""

import datetime

import inngest
import tests.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    step_1a_counter = 0
    step_1b_counter = 0
    step_2a_counter = 0
    step_2b_counter = 0
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

        def _step_1a() -> str:
            state.step_1a_counter += 1
            return "1a"

        def _step_1b() -> str:
            state.step_1b_counter += 1
            return "1b"

        def _step_2a() -> str:
            state.step_2a_counter += 1
            return "2a"

        def _step_2b() -> str:
            state.step_2b_counter += 1
            return "2b"

        def _wrapper_a() -> list[str]:
            out = []
            out.append(step.run("1a", _step_1a))
            out.append(step.run("1b", _step_1b))
            return out

        def _wrapper_b() -> list[str]:
            out = []
            out.append(step.run("2a", _step_2a))
            out.append(step.run("2b", _step_2b))
            return out

        state.parallel_output = step.parallel((_wrapper_a, _wrapper_b))

        def _step_after() -> None:
            state.step_after_counter += 1

        step.run("after", _step_after)

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

        async def _step_1a() -> str:
            state.step_1a_counter += 1
            return "1a"

        async def _step_1b() -> str:
            state.step_1b_counter += 1
            return "1b"

        async def _step_2a() -> str:
            state.step_2a_counter += 1
            return "2a"

        async def _step_2b() -> str:
            state.step_2b_counter += 1
            return "2b"

        async def _wrapper_a() -> list[str]:
            out = []
            out.append(await step.run("1a", _step_1a))
            out.append(await step.run("1b", _step_1b))
            return out

        async def _wrapper_b() -> list[str]:
            out = []
            out.append(await step.run("2a", _step_2a))
            out.append(await step.run("2b", _step_2b))
            return out

        state.parallel_output = await step.parallel((_wrapper_a, _wrapper_b))

        async def _step_after() -> None:
            state.step_after_counter += 1

        await step.run("after", _step_after)

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))

        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        assert state.parallel_output == (
            ["1a", "1b"],
            ["2a", "2b"],
        )
        assert state.step_1a_counter == 1
        assert state.step_1b_counter == 1
        assert state.step_2a_counter == 1
        assert state.step_2b_counter == 1
        assert state.step_after_counter == 1

    if is_sync:
        fn = [fn_sync, fn_child_sync]
    else:
        fn = [fn_async, fn_child_async]

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
