import asyncio
import json

import inngest
import test_core
from inngest.experimental.connect import ConnectionState, connect

from .base import BaseTest


class TestWaitForExecutionRequest(BaseTest):
    async def test(self) -> None:
        """
        Test that the worker waits for an execution request to complete before
        closing.
        """

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )
        event_name = test_core.random_suffix("event")
        state = test_core.BaseState()
        closed_event = asyncio.Event()

        @client.create_function(
            fn_id="fn",
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context, step: inngest.Step) -> str:
            state.run_id = ctx.run_id

            # Suspend the function until the connection is closing.
            await closed_event.wait()

            return "Hello"

        conn = connect([(client, [fn])])
        task = asyncio.create_task(conn.start())
        self.addCleanup(conn.closed)
        self.addCleanup(task.cancel)
        await conn.wait_for_state(ConnectionState.ACTIVE)

        await client.send(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()

        await conn.close()

        # This sleep is probably not needed, but we'll wait slightly longer just
        # in case.
        await asyncio.sleep(1)
        closed_event.set()

        # Run still completed.
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        assert json.loads(run.output) == "Hello"
