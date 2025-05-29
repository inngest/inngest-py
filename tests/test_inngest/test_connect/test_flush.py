import asyncio
import json

import inngest
import pytest
import structlog
import test_core
from inngest.experimental.connect import ConnectionState, connect

from .base import BaseTest


class _State(test_core.BaseState):
    ws_aborted: bool = False


class TestFlush(BaseTest):
    # Need to extend the timeout because messages are only flushed after their
    # lease expires.
    @pytest.mark.timeout(10, method="thread")
    async def test(self) -> None:
        """
        An unexpected WebSocket disconnect (a.k.a. abort) should trigger a
        reconnect. That reconnect should eventually succeed.
        """

        proxies = await self.create_proxies()

        client = inngest.Inngest(
            api_base_url=proxies.http_proxy.origin,
            app_id="app",
            is_production=False,
            logger=structlog.get_logger(),
        )
        event_name = test_core.random_suffix("event")
        state = _State()

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> str:
            state.run_id = ctx.run_id

            while not state.ws_aborted:  # noqa: ASYNC110
                await asyncio.sleep(0.1)

            return "hi"

        # Startup.
        conn = connect([(client, [fn])])
        task = asyncio.create_task(conn.start())
        self.addCleanup(conn.close, wait=True)
        self.addCleanup(task.cancel)
        await conn.wait_for_state(ConnectionState.ACTIVE)

        # Trigger the function.
        await client.send(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()

        # Abort the WS conn.
        await proxies.ws_proxy.abort_conns()
        state.ws_aborted = True

        # Wait for the run to complete.
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        assert json.loads(run.output) == "hi"

        # Ensure the flush API endpoint was called.
        flush_request_exists = False
        for req in proxies.requests:
            if req.path == "/v0/connect/flush":
                flush_request_exists = True
                break
        assert flush_request_exists
