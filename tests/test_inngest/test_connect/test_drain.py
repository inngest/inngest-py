import asyncio

import inngest
import pytest
import test_core
from inngest.connect import ConnectionState, connect
from inngest.connect._internal import connect_pb2

from .base import BaseTest, collect_states


class TestDrain(BaseTest):
    @pytest.mark.timeout(10, method="thread")
    async def test(self) -> None:
        """
        A drain should trigger a reconnect.
        """

        proxies = await self.create_proxies()

        client = inngest.Inngest(
            api_base_url=proxies.http_proxy.origin,
            app_id="app",
            is_production=False,
        )

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn(ctx: inngest.Context) -> None:
            pass

        conn = connect([(client, [fn])])
        states = collect_states(conn)
        task = asyncio.create_task(conn.start())
        self.addCleanup(conn.close, wait=True)
        self.addCleanup(task.cancel)

        # Initial connection.
        await conn.wait_for_state(ConnectionState.ACTIVE)
        await test_core.wait_for_len(lambda: proxies.requests, 1)

        # Simulate the drain message.
        await proxies.ws_proxy.send_to_clients(
            connect_pb2.ConnectMessage(
                kind=connect_pb2.GatewayMessageType.GATEWAY_CLOSING
            ).SerializeToString()
        )

        # Post-drain connection.
        await test_core.wait_for_len(lambda: proxies.requests, 2)
        await conn.wait_for_state(ConnectionState.ACTIVE)

        assert states == [
            ConnectionState.CONNECTING,
            ConnectionState.ACTIVE,
            ConnectionState.CONNECTING,
            ConnectionState.ACTIVE,
        ]
