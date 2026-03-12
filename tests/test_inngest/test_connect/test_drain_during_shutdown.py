import asyncio

import inngest
import pytest
import test_core
from inngest.connect import ConnectionState, connect
from inngest.connect._internal import connect_pb2
from inngest.connect._internal.connection import (
    WorkerConnectionImpl,  # pyright: ignore[reportPrivateUsage]
)

from .base import BaseTest, collect_states


class TestDrainDuringGracefulShutdown(BaseTest):
    @pytest.mark.timeout(10, method="thread")
    async def test(self) -> None:
        """
        When the SDK is gracefully shutting down (CLOSING state) and receives a
        GATEWAY_CLOSING (drain) message, it should reconnect to a new gateway so
        that heartbeats and lease extensions continue on a live WS connection
        while in-flight work completes.
        """

        proxies = await self.create_proxies()

        client = inngest.Inngest(
            api_base_url=proxies.http_proxy.origin,
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn(ctx: inngest.Context) -> None:
            pass

        conn = connect([(client, [fn])])
        task = asyncio.create_task(conn.start())
        self.addConnCleanup(conn, task)

        # Wait for initial connection.
        await asyncio.wait_for(
            conn.wait_for_state(ConnectionState.ACTIVE),
            timeout=2,
        )
        await test_core.wait_for_len(lambda: proxies.requests, 1)

        # Simulate in-flight work by incrementing pending_request_count.
        # This prevents handlers from closing immediately during shutdown.
        assert isinstance(conn, WorkerConnectionImpl)
        conn._state.pending_request_count.value = 1  # pyright: ignore[reportPrivateUsage]

        # Initiate graceful shutdown (does not wait for completion).
        await conn.close()
        await asyncio.wait_for(
            conn.wait_for_state(ConnectionState.CLOSING),
            timeout=2,
        )

        # Simulate the server draining while we're shutting down.
        proxies.ws_proxy.send_to_clients(
            connect_pb2.ConnectMessage(
                kind=connect_pb2.GatewayMessageType.GATEWAY_CLOSING
            ).SerializeToString()
        )

        # Verify reconnection occurs: a new start request is sent and
        # the connection reaches ACTIVE again.
        await test_core.wait_for_len(lambda: proxies.requests, 2)
        await asyncio.wait_for(
            conn.wait_for_state(ConnectionState.ACTIVE),
            timeout=2,
        )

        # Complete the in-flight work so shutdown can finish.
        conn._state.pending_request_count.value = 0  # pyright: ignore[reportPrivateUsage]

        # Verify clean shutdown.
        await asyncio.wait_for(
            conn.wait_for_state(ConnectionState.CLOSED),
            timeout=5,
        )
