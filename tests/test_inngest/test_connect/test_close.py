import asyncio
import json

import inngest
import test_core
from inngest.connect import ConnectionState, connect
from test_core import http_proxy

from .base import BaseTest, collect_states


class TestWaitForExecutionRequest(BaseTest):
    async def test_after_initial_connection(self) -> None:
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
        async def fn(ctx: inngest.Context) -> str:
            state.run_id = ctx.run_id

            # Suspend the function until the connection is closing.
            await closed_event.wait()

            return "Hello"

        conn = connect([(client, [fn])])
        states = collect_states(conn)
        task = asyncio.create_task(conn.start())
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

        await conn.closed()
        assert states == [
            ConnectionState.CONNECTING,
            ConnectionState.ACTIVE,
            ConnectionState.CLOSING,
            ConnectionState.CLOSED,
        ]

    async def test_without_initial_connection(self) -> None:
        """
        Test that the worker gracefully closes even if it never establishes a
        connection.
        """

        api_called = False

        def on_request(
            *,
            body: bytes | None,
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> http_proxy.Response:
            nonlocal api_called
            api_called = True

            # Always return a 500, which prevents the worker from establishing a
            # connection.
            return http_proxy.Response(
                body=b"",
                headers={},
                status_code=500,
            )

        proxy = http_proxy.Proxy(on_request).start()

        client = inngest.Inngest(
            api_base_url=proxy.origin,
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(
                event=test_core.random_suffix("event"),
            ),
        )
        async def fn(ctx: inngest.Context) -> None:
            pass

        conn = connect([(client, [fn])])
        states = collect_states(conn)
        task = asyncio.create_task(conn.start())
        self.addCleanup(task.cancel)

        await test_core.wait_for_truthy(lambda: api_called)
        await conn.close()
        await conn.closed()
        assert states == [
            ConnectionState.CONNECTING,
            ConnectionState.CLOSING,
            ConnectionState.CLOSED,
        ]
