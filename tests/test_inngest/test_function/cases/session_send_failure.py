"""
Handlers must be able to catch a failed send as StepError and recover. Invalid
inherited sessions should fail the send step, rather than fail the whole
function before its error handler can run.
"""

import json

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    state = base.BaseState()
    child_ran = False

    @client.create_function(
        fn_id=f"{test_name}/child",
        retries=0,
        trigger=inngest.TriggerEvent(event=f"{event_name}/child"),
    )
    def child(ctx: inngest.ContextSync) -> None:
        nonlocal child_ran
        child_ran = True

    def parent_sync(ctx: inngest.ContextSync) -> str:
        state.run_id = ctx.run_id
        ctx.sessions["conversation"] = ""
        try:
            ctx.step.send_event(
                "child", inngest.Event(name=f"{event_name}/child")
            )
        except inngest.StepError as err:
            assert "session IDs cannot be empty" in err.message
            return "recovered"
        raise AssertionError("The send should have failed")

    async def parent_async(ctx: inngest.Context) -> str:
        state.run_id = ctx.run_id
        ctx.sessions["conversation"] = ""
        try:
            await ctx.step.send_event(
                "child", inngest.Event(name=f"{event_name}/child")
            )
        except inngest.StepError as err:
            assert "session IDs cannot be empty" in err.message
            return "recovered"
        raise AssertionError("The send should have failed")

    parent = client.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )(parent_sync if is_sync else parent_async)

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        assert json.loads(run.output) == "recovered"
        assert not child_ran

    return base.Case(fn=[parent, child], name=test_name, run_test=run_test)
