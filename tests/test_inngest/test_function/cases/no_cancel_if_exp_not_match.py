"""
Don't cancel the run if the function's cancel expression isn't matched
"""

import asyncio
import time

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    is_done: bool = False


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = test_name
    state = _State()

    @client.create_function(
        cancel=[
            inngest.Cancel(
                event=f"{event_name}.cancel",
                if_exp="event.data.id == async.data.id",
            ),
        ],
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id

        # Wait a little bit to allow the cancel event to be sent.
        time.sleep(3)

        # The test will need to wait for this function's logic to finish even
        # though it's cancelled. Without this, Tornado will error due to logic
        # still running after the test is done.
        state.is_done = True

    @client.create_function(
        cancel=[
            inngest.Cancel(
                event=f"{event_name}.cancel",
                if_exp="event.data.id == async.data.id",
            ),
        ],
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id

        # Wait a little bit to allow the cancel event to be sent.
        await asyncio.sleep(3)

        # The test will need to wait for this function's logic to finish even
        # though it's cancelled. Without this, Tornado will error due to logic
        # still running after the test is done.
        state.is_done = True

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name, data={"id": 123}))
        run_id = await state.wait_for_run_id()
        self.client.send_sync(
            inngest.Event(name=f"{event_name}.cancel", data={"id": 456})
        )
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        def assert_is_done() -> None:
            assert state.is_done

        await base.wait_for(assert_is_done)

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
