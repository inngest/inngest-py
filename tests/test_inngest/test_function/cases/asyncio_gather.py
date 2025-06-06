import asyncio
import datetime

import inngest
import pytest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    after_counter = 0
    fast_counter = 0
    output: object = None
    slow_counter = 0


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
        _experimental_execution=True,
    )
    async def fn_child_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        await step.sleep("sleep", datetime.timedelta(seconds=1))

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
        _experimental_execution=True,
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_id = ctx.run_id

        async def fast() -> str:
            state.fast_counter += 1
            return "fast"

        async def slow() -> str:
            state.slow_counter += 1
            await asyncio.sleep(1)
            return "slow"

        state.output = await asyncio.gather(
            asyncio.create_task(
                step.invoke("invoke", function=fn_child_async),
            ),
            asyncio.create_task(step.run("slow", slow)),
            asyncio.create_task(step.run("fast", fast)),
            asyncio.create_task(
                step.sleep("sleep", datetime.timedelta(seconds=1))
            ),
            asyncio.create_task(
                step.sleep_until(
                    "sleep_until",
                    datetime.datetime.now() + datetime.timedelta(seconds=1),
                )
            ),
            asyncio.create_task(
                step.wait_for_event(
                    "wait",
                    event="never",
                    timeout=datetime.timedelta(seconds=1),
                )
            ),
        )

        def after() -> None:
            state.after_counter += 1

        await step.run("after", after)

    # We're gonna remove this feature anyway.
    @pytest.mark.xfail
    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )

        assert state.fast_counter == 1
        assert state.slow_counter == 1
        assert state.after_counter == 1
        assert state.output == [None, "slow", "fast", None, None, None]

    if is_sync:
        # This test is not applicable for sync functions
        fn = []
    else:
        fn = [fn_async, fn_child_async]

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
