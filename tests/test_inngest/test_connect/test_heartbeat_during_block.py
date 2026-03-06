import asyncio

import inngest
import pytest
import test_core
from inngest.connect import ConnectionState
from inngest.connect._internal import connect_pb2
from inngest.connect._internal.connection import WorkerConnectionImpl

from .base import BaseTest


class TestHeartbeatDuringBlock(BaseTest):
    @pytest.mark.timeout(15, method="thread")
    async def test_heartbeat_unaffected_by_main_thread_block(self) -> None:
        """
        Blocking the main thread must not prevent heartbeats from being sent.
        Connect internals (including heartbeats) run in an isolated thread, so
        a blocking call in user code should not affect them.
        """

        proxies = await self.create_proxies()

        client = inngest.Inngest(
            api_base_url=proxies.http_proxy.origin,
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )

        @client.create_function(
            fn_id="fn",
            retries=0,
            trigger=inngest.TriggerEvent(
                event=test_core.random_suffix("event")
            ),
        )
        async def fn(ctx: inngest.Context) -> None:
            pass

        # Directly use `WorkerConnectionImpl` instead of `connect` because we
        # want to override the heartbeat interval (to make the test faster).
        conn = WorkerConnectionImpl(
            [(client, [fn])],
            _test_only_heartbeat_interval_sec=1,
        )

        task = asyncio.create_task(conn.start())
        self.addConnCleanup(conn, task)
        await conn.wait_for_state(ConnectionState.ACTIVE)

        heartbeats_before = _count_heartbeats(
            proxies.ws_proxy.forwarded_messages
        )

        # Intentionally block this thread until we get 4 more heartbeats. This
        # proves that the main thread cannot block Connect's internals.
        while True:
            heartbeats_after = _count_heartbeats(
                proxies.ws_proxy.forwarded_messages
            )
            if heartbeats_after - heartbeats_before >= 4:
                break


def _count_heartbeats(raw_msgs: list[bytes]) -> int:
    count = 0
    for raw_msg in raw_msgs:
        msg = connect_pb2.ConnectMessage()
        msg.ParseFromString(raw_msg)
        if msg.kind == connect_pb2.GatewayMessageType.WORKER_HEARTBEAT:
            count += 1
    return count
