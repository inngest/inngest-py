import asyncio

import inngest
import tests.helper
from inngest._internal import const

from . import base


class _State(base.BaseState):
    parallel_result: object = None
    step_1a_counter = 0
    step_1b_counter = 0
    step_2_counter = 0


def create(
    client: inngest.Inngest,
    framework: const.Framework,
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

        async def _step_1a() -> int:
            await asyncio.sleep(1)
            state.step_1a_counter += 1
            return 1

        def _step_1b() -> int:
            state.step_1b_counter += 1
            return 2

        state.parallel_result = await asyncio.gather(
            step.run("1a", _step_1a),
            step.run("1b", _step_1b),
            step.sleep("1c", 1000),
            step.wait_for_event("1d", event="foo", timeout=1000),
        )

        def _step_2() -> None:
            state.step_2_counter += 1

        await step.run("2", _step_2)

    def run_test(self: base.TestClass) -> None:
        if is_sync:
            # This test is not applicable for sync functions
            return

        self.client.send_sync(inngest.Event(name=event_name))
        tests.helper.client.wait_for_run_status(
            state.wait_for_run_id(),
            tests.helper.RunStatus.COMPLETED,
        )

        assert state.step_1a_counter == 1
        assert state.step_1b_counter == 1
        assert state.step_2_counter == 1
        assert state.parallel_result == [1, 2, None, None]

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
