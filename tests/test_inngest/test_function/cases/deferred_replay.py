"""
Replay and duplicate defer IDs must not schedule extra children.

The first call's data wins when another call repeats its ID.
"""

import asyncio

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
    received: list[str] = []
    parent_entries = 0

    def receive(ctx: inngest.Context | inngest.ContextSync) -> None:
        child_state.run_id = ctx.run_id
        received.append(str(ctx.event.data["label"]))

    target = create_defer(client, fn_id=f"{name}-child", retries=0)(
        receive if is_sync else base.asyncify(receive)
    )

    def schedule(ctx: inngest.Context | inngest.ContextSync) -> None:
        nonlocal parent_entries
        parent_entries += 1
        parent_state.run_id = ctx.run_id
        ctx.defer("child", function=target, data={"label": "first"})
        ctx.defer("child", function=target, data={"label": "duplicate"})

    def sync(ctx: inngest.ContextSync) -> None:
        schedule(ctx)
        ctx.step.run("checkpoint", lambda: None)

    async def async_fn(ctx: inngest.Context) -> None:
        schedule(ctx)

        async def checkpoint() -> None:
            pass

        await ctx.step.run("checkpoint", checkpoint)

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
        # Allow an erroneous duplicate child to arrive before checking count.
        await asyncio.sleep(1)
        assert received == ["first"]

    return base.Case(fn=[parent, target], name=name, run_test=run_test)
