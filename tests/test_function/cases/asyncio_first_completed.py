"""
We don't support `async.gather` yet. This test demonstrates the bug that happens
when using `async.gather`: a step is executed twice
"""

import asyncio
import datetime

import inngest
import tests.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    request_counter = 0
    after_counter = 0
    done_count = 0
    done_result: object = None
    fast_counter = 0
    pending_count = 0
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
        await asyncio.sleep(1)

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

        done, pending = await asyncio.wait(
            set(
                [
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
                            datetime.datetime.now()
                            + datetime.timedelta(seconds=1),
                        )
                    ),
                    asyncio.create_task(
                        step.wait_for_event(
                            "wait",
                            event="never",
                            timeout=datetime.timedelta(seconds=1),
                        )
                    ),
                ]
            ),
            return_when=asyncio.FIRST_COMPLETED,
        )
        state.done_count = len(done)
        state.pending_count = len(pending)
        state.done_result = done.pop().result()

        def after() -> None:
            state.after_counter += 1

        await step.run("after", after)

    async def run_test(self: base.TestClass) -> None:
        if is_sync:
            # This test is not applicable for sync functions
            return

        self.client.send_sync(inngest.Event(name=event_name))
        tests.helper.client.wait_for_run_status(
            state.wait_for_run_id(),
            tests.helper.RunStatus.COMPLETED,
        )

        assert state.fast_counter == 1
        assert state.slow_counter == 1
        assert state.after_counter == 1
        assert state.done_count == 1
        assert state.pending_count == 5
        assert state.done_result == "fast"

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
