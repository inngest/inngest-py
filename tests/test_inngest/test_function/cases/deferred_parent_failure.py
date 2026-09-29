"""
Valid deferred work must still run when its parent fails.
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

    def receive(ctx: inngest.Context | inngest.ContextSync) -> None:
        child_state.run_id = ctx.run_id
        assert ctx.parents[0].run_id == parent_state.run_id
        assert ctx.event.data == {"message": "survived"}

    target = create_defer(client, fn_id=f"{name}-child", retries=0)(
        receive if is_sync else base.asyncify(receive)
    )

    def run(ctx: inngest.Context | inngest.ContextSync) -> None:
        parent_state.run_id = ctx.run_id
        ctx.defer("child", function=target, data={"message": "survived"})
        raise inngest.NonRetriableError("intentional parent failure")

    parent = client.create_function(
        fn_id=name, retries=0, trigger=inngest.TriggerEvent(event=event_name)
    )(run if is_sync else base.asyncify(run))

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        parent_id = await parent_state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            parent_id, test_core.helper.RunStatus.FAILED
        )
        child_id = await child_state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            child_id, test_core.helper.RunStatus.COMPLETED
        )

    return base.Case(fn=[parent, target], name=name, run_test=run_test)
