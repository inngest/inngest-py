import datetime

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
    fn_id = base.create_fn_id(test_name)
    state = base.BaseState()

    # Used to know how many runs started.
    run_ids = set[str]()

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        singleton=inngest.Singleton(mode="cancel"),
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id
        run_ids.add(ctx.run_id)

        # Sleep long enough to ensure that the second run will be cancelled.
        ctx.step.sleep("zzz", datetime.timedelta(seconds=5))

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        singleton=inngest.Singleton(mode="cancel"),
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id
        run_ids.add(ctx.run_id)

        # Sleep long enough to ensure that the second run will be cancelled.
        await ctx.step.sleep("zzz", datetime.timedelta(seconds=5))

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync([inngest.Event(name=event_name)])

        first_run_id = await state.wait_for_run_id(
            timeout=datetime.timedelta(seconds=5)
        )
        state.run_id = None

        self.client.send_sync([inngest.Event(name=event_name)])

        await test_core.helper.client.wait_for_run_status(
            first_run_id,
            test_core.helper.RunStatus.CANCELLED,
        )

        second_run_id = await state.wait_for_run_id(
            timeout=datetime.timedelta(seconds=5)
        )
        assert len(run_ids) == 2

        await test_core.helper.client.wait_for_run_status(
            second_run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
