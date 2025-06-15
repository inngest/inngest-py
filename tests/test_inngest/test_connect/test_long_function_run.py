import asyncio

import inngest
import pytest
import test_core
from inngest.connect import ConnectionState, connect

from .base import BaseTest


class TestLongFunctionRun(BaseTest):
    @pytest.mark.timeout(30, method="thread")
    async def test(self) -> None:
        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )
        event_name = test_core.random_suffix("event")
        state = test_core.BaseState()

        @client.create_function(
            fn_id="fn",
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> None:
            state.run_id = ctx.run_id

            # Sleep for long enough to require lease extensions.
            await asyncio.sleep(20)

        conn = connect([(client, [fn])])
        task = asyncio.create_task(conn.start())
        self.addCleanup(conn.close, wait=True)
        self.addCleanup(task.cancel)

        await conn.wait_for_state(ConnectionState.ACTIVE)

        # Trigger the function and wait for it to complete.
        await client.send(inngest.Event(name=event_name))
        await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )
