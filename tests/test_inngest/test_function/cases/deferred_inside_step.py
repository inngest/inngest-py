"""
A defer inside step.run must survive its callback being skipped on replay.
"""

import inngest
import test_core.helper
from inngest._internal import server_lib
from inngest.experimental import create_defer

from . import base


def create(
    client: inngest.Inngest, framework: server_lib.Framework, is_sync: bool
) -> base.Case:
    name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, name)
    parent_state = base.BaseState()
    child_state = base.BaseState()
    callbacks = 0
    parent_entries = 0

    def receive(ctx: inngest.Context | inngest.ContextSync) -> None:
        child_state.run_id = ctx.run_id
        assert ctx.event.data == {"from": "step"}

    target = create_defer(client, fn_id=f"{name}-child", retries=0)(
        receive if is_sync else base.asyncify(receive)
    )

    def work(ctx: inngest.Context | inngest.ContextSync) -> None:
        nonlocal callbacks
        callbacks += 1
        ctx.defer("child", function=target, data={"from": "step"})

    def sync(ctx: inngest.ContextSync) -> None:
        nonlocal parent_entries
        parent_entries += 1
        parent_state.run_id = ctx.run_id
        ctx.step.run("work", lambda: work(ctx))

    async def async_fn(ctx: inngest.Context) -> None:
        nonlocal parent_entries
        parent_entries += 1
        parent_state.run_id = ctx.run_id

        async def callback() -> None:
            work(ctx)

        await ctx.step.run("work", callback)

    parent = client.create_function(
        fn_id=name, retries=0, trigger=inngest.TriggerEvent(event=event_name)
    )(sync if is_sync else async_fn)

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        parent_id = await parent_state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            parent_id, test_core.helper.RunStatus.COMPLETED
        )
        child_id = await child_state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            child_id, test_core.helper.RunStatus.COMPLETED
        )
        assert parent_entries >= 2
        assert callbacks == 1

    return base.Case(fn=[parent, target], name=name, run_test=run_test)
