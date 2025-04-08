import asyncio
import time

import inngest
import test_core
from inngest.experimental.connect import ConnectionState, connect

from .base import BaseTest


class TestConcurrentSyncFunctions(BaseTest):
    async def test_cloud(self) -> None:
        """
        Test that sync functions can be run concurrently. Under-the-hood, this
        is accomplished with a ThreadPoolExecutor that is shared across all
        functions.
        """

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )
        event_name = test_core.random_suffix("event")
        run_ids = set[str]()

        @client.create_function(
            fn_id="fn",
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        def fn(ctx: inngest.Context, step: inngest.StepSync) -> None:
            run_ids.add(ctx.run_id)

            # This will loop forever if the function run is blocking the event
            # loop, causing the test to timeout.
            while True:
                if len(run_ids) == 2:
                    break

        conn = connect([(client, [fn])])
        task = asyncio.create_task(conn.start())
        self.addCleanup(conn.close, wait=True)
        self.addCleanup(task.cancel)
        await conn.wait_for_state(ConnectionState.ACTIVE)

        # Trigger the function and wait for it to complete.
        await client.send(
            [
                inngest.Event(name=event_name),
                inngest.Event(name=event_name),
            ]
        )

        def assert_runs() -> None:
            assert len(run_ids) == 2

        await test_core.wait_for(assert_runs)

        await test_core.helper.client.wait_for_run_status(
            run_ids.pop(),
            test_core.helper.RunStatus.COMPLETED,
        )
        await test_core.helper.client.wait_for_run_status(
            run_ids.pop(),
            test_core.helper.RunStatus.COMPLETED,
        )
