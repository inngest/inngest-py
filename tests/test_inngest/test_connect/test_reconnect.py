import asyncio
import typing

import inngest
import pytest
import test_core
from inngest.experimental.connect import ConnectionState, connect
from inngest.experimental.connect.connection import (
    _WebSocketWorkerConnection,
)

from .base import BaseTest


class TestReconnect(BaseTest):
    @pytest.mark.timeout(10, method="thread")
    async def test_reconnect(self) -> None:
        """
        An unexpected WebSocket disconnect (a.k.a. abort) should trigger a
        reconnect. That reconnect should eventually succeed.
        """

        proxies = await self.create_proxies()

        client = inngest.Inngest(
            api_base_url=f"http://0.0.0.0:{proxies.http_proxy.port}",
            app_id="app",
            is_production=False,
        )

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn(ctx: inngest.Context, step: inngest.Step) -> None:
            pass

        conn = connect([(client, [fn])])

        states: list[ConnectionState] = []
        if isinstance(conn, _WebSocketWorkerConnection):
            conn._state.conn_state.on_change(
                lambda _, state: states.append(state)
            )

        task = asyncio.create_task(conn.start())
        self.addCleanup(conn.close, wait=True)
        self.addCleanup(task.cancel)

        # Initial connection.
        await conn.wait_for_state(ConnectionState.ACTIVE)
        await test_core.wait_for_len(lambda: proxies.requests, 1)

        # Abort all WS conns. This avoids graceful shutdown.
        await proxies.ws_proxy.abort_conns()

        # Ensure we enter the reconnecting state.
        await conn.wait_for_state(ConnectionState.RECONNECTING)

        # Post-reconnect connection.
        await test_core.wait_for_len(lambda: proxies.requests, 2)
        await conn.wait_for_state(ConnectionState.ACTIVE)

        assert states == [
            ConnectionState.CONNECTING,
            ConnectionState.ACTIVE,
            ConnectionState.RECONNECTING,
            ConnectionState.CONNECTING,
            ConnectionState.ACTIVE,
        ]
