import asyncio
import dataclasses
import json

import inngest
import pytest
import test_core
from inngest.connect import ConnectionState, connect
from inngest.connect._internal import connect_pb2
from test_core import http_proxy

from .base import BaseTest, collect_states


class TestWaitForExecutionRequest(BaseTest):
    async def test_after_initial_connection(self) -> None:
        """
        Test that the worker waits for an execution request to complete before
        closing.
        """

        proxies = await self.create_proxies()
        client = inngest.Inngest(
            api_base_url=proxies.http_proxy.origin,
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

        # Assert that we sent the worker pause message, which tells the Inngest
        # Server not to send any more execution requests
        sent_worker_pause = False
        for msg_byt in proxies.ws_proxy.forwarded_messages:
            msg = connect_pb2.ConnectMessage()
            msg.ParseFromString(msg_byt)
            if msg.kind == connect_pb2.GatewayMessageType.WORKER_PAUSE:
                sent_worker_pause = True
                break
        assert sent_worker_pause is True

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

    @pytest.mark.timeout(30, method="thread")
    async def test_wait_for_execution_request(self) -> None:
        """
        Test that the worker waits for an execution request to complete before
        closing. We'll assert this by ensuring that heartbeats and lease extends
        continue after close
        """

        proxies = await self.create_proxies()
        client = inngest.Inngest(
            api_base_url=proxies.http_proxy.origin,
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )
        event_name = test_core.random_suffix("event")

        class _State(test_core.BaseState):
            after_sleep: bool = False

        state = _State()

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> None:
            state.run_id = ctx.run_id

            # Intentionally keep the execution request going long enough for
            # heartbeats and lease extends to send after Connect close
            await asyncio.sleep(20)

            state.after_sleep = True

        # Start app
        conn = connect([(client, [fn])])
        task = asyncio.create_task(conn.start())
        self.addCleanup(task.cancel)
        await conn.wait_for_state(ConnectionState.ACTIVE)

        # Trigger the function
        await client.send(inngest.Event(name=event_name))
        await state.wait_for_run_id()

        counts_before_close = count_messages(
            proxies.ws_proxy.forwarded_messages
        )

        # Close Connect
        await conn.close()
        await conn.wait_for_state(ConnectionState.CLOSING)
        await conn.closed()

        assert state.after_sleep is True
        counts_after_close = count_messages(proxies.ws_proxy.forwarded_messages)

        # Heartbeats continued after close, since the function was still running
        assert (
            counts_after_close.heartbeats - counts_before_close.heartbeats >= 2
        )

        # No lease extends before close since the function had just started
        # running
        assert counts_before_close.lease_extends == 0

        # Lease extends continued after close, since the function was still
        # running
        assert counts_after_close.lease_extends >= 4


@dataclasses.dataclass
class MessageCounts:
    heartbeats: int
    lease_extends: int


def count_messages(
    raw_msgs: list[bytes],
) -> MessageCounts:
    counts = MessageCounts(heartbeats=0, lease_extends=0)
    for raw_msg in raw_msgs:
        msg = connect_pb2.ConnectMessage()
        msg.ParseFromString(raw_msg)
        if msg.kind == connect_pb2.GatewayMessageType.WORKER_HEARTBEAT:
            counts.heartbeats += 1
        elif (
            msg.kind
            == connect_pb2.GatewayMessageType.WORKER_REQUEST_EXTEND_LEASE
        ):
            counts.lease_extends += 1
    return counts
