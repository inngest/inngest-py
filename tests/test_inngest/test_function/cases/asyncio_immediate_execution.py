"""
Test that we're properly handling disabled_immediate_execution. That's how the
Server says "plan non-parallel steps because we previously had parallel steps".
This is necessary because the Server schedules a "discovery" step after each
parallel step
"""

import asyncio

import inngest
import pytest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    request_counter = 0


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
        state.request_counter += 1

        await step.run("a", lambda: None)
        await step.run("b", lambda: None)

    # We're gonna remove this feature anyway.
    @pytest.mark.xfail
    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )

        assert state.request_counter == 3

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
