import asyncio
import dataclasses
import json

import inngest
import test_core
from inngest.experimental import dev_server
from inngest.experimental.connect import ConnectionState, connect

from .base import BaseTest


@dataclasses.dataclass
class _State(test_core.BaseState):
    step_counter = 0


class TestFunctionRun(BaseTest):
    async def test_cloud(self) -> None:
        """
        Test that a function can be run in the Cloud. We're still using the Dev
        Server, but that's OK because execution requests are identical between
        Cloud and the Dev Server (since there are no headers).
        """

        client = inngest.Inngest(
            api_base_url=dev_server.server.origin,
            app_id=test_core.random_suffix("app"),
            event_api_base_url=dev_server.server.origin,
            event_key="foo",
            signing_key="deadbeef",
        )
        event_name = test_core.random_suffix("event")
        state = _State()

        @client.create_function(
            fn_id="fn",
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> str:
            state.run_id = ctx.run_id

            async def step_a() -> str:
                state.step_counter += 1
                return "Alice"

            name = await ctx.step.run("a", step_a)
            return f"Hello {name}"

        conn = connect([(client, [fn])])
        task = asyncio.create_task(conn.start())
        self.addCleanup(conn.close, wait=True)
        self.addCleanup(task.cancel)
        await conn.wait_for_state(ConnectionState.ACTIVE)

        # Trigger the function and wait for it to complete.
        await client.send(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        assert json.loads(run.output) == "Hello Alice"
        self.assertEqual(state.step_counter, 1)

    async def test_dev(self) -> None:
        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )
        event_name = test_core.random_suffix("event")
        state = _State()

        @client.create_function(
            fn_id="fn",
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> str:
            state.run_id = ctx.run_id

            async def step_a() -> str:
                state.step_counter += 1
                return "Alice"

            name = await ctx.step.run("a", step_a)
            return f"Hello {name}"

        conn = connect([(client, [fn])])
        task = asyncio.create_task(conn.start())
        self.addCleanup(conn.close, wait=True)
        self.addCleanup(task.cancel)

        await conn.wait_for_state(ConnectionState.ACTIVE)

        # Trigger the function and wait for it to complete.
        await client.send(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        assert json.loads(run.output) == "Hello Alice"
        self.assertEqual(state.step_counter, 1)
