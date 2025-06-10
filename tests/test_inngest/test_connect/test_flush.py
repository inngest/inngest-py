import asyncio
import json

import inngest
import pytest
import test_core
from inngest.connect import ConnectionState, connect

from .base import BaseTest


class _State(test_core.BaseState):
    ws_aborted: bool = False


class TestFlush(BaseTest):
    # Need to extend the timeout because messages are only flushed after their
    # lease expires.
    @pytest.mark.timeout(10, method="thread")
    async def test_connection_loss(self) -> None:
        """
        An unexpected WebSocket disconnect (e.g. abort) should trigger a
        reconnect. That reconnect should eventually succeed.
        """

        proxies = await self.create_proxies()

        client = inngest.Inngest(
            api_base_url=proxies.http_proxy.origin,
            app_id=test_core.random_suffix("app"),
            is_production=False,
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

    # Need to extend the timeout because messages are only flushed after their
    # lease expires.
    @pytest.mark.timeout(10, method="thread")
    async def test_acked_messages_are_not_flushed(self) -> None:
        """
        Acked messages are not flushed when the connection is lost. Internally,
        this means that acked messages are removed from the buffer before
        flushing.
        """

        proxies = await self.create_proxies()

        client = inngest.Inngest(
            api_base_url=proxies.http_proxy.origin,
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )
        event_name = test_core.random_suffix("event")
        state = test_core.BaseState()

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> str:
            state.run_id = ctx.run_id
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

        # Wait for the run to complete.
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        assert json.loads(run.output) == "hi"

        # Wait for the lease to expire. The lease expiration is 5 seconds.
        await asyncio.sleep(6)

        # Ensure the flush API endpoint was called.
        flush_request_exists = False
        for req in proxies.requests:
            if req.path == "/v0/connect/flush":
                flush_request_exists = True
                break
        assert flush_request_exists is False
