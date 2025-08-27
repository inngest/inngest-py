# pyright: reportPrivateUsage=false

import asyncio
from typing import Any

import inngest
import pytest
import test_core
from inngest.connect import ConnectionState, connect
from inngest.connect._internal import connect_pb2

from .base import BaseTest


class TestLeaseExtendFailure(BaseTest):
    @pytest.mark.timeout(10, method="thread")
    async def test_lease_extend_failure_removes_pending_request(self) -> None:
        """Test that a lease extension nack removes the pending request."""

        proxies = await self.create_proxies()

        client = inngest.Inngest(
            api_base_url=proxies.http_proxy.origin,
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )
        event_name = test_core.random_suffix("event")

        state = test_core.BaseState()
        run_task: asyncio.Task[Any] | None = None

        @client.create_function(
            fn_id="fn",
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> None:
            nonlocal run_task
            run_task = asyncio.current_task()
            state.run_id = ctx.run_id
            await asyncio.sleep(5)

        conn = connect([(client, [fn])])
        task = asyncio.create_task(conn.start())
        self.addCleanup(conn.close, wait=True)
        self.addCleanup(task.cancel)

        await conn.wait_for_state(ConnectionState.ACTIVE)
        await test_core.wait_for_len(lambda: proxies.requests, 1)

        await client.send(inngest.Event(name=event_name))

        await state.wait_for_run_id()

        request_id = get_request_id(proxies.ws_proxy.forwarded_messages)
        assert request_id != ""

        # Failed lease extension payload
        await proxies.ws_proxy.send_to_clients(
            connect_pb2.ConnectMessage(
                kind=connect_pb2.GatewayMessageType.WORKER_REQUEST_EXTEND_LEASE_ACK,
                payload=connect_pb2.WorkerRequestExtendLeaseAckData(
                    request_id=request_id,
                    new_lease_id=None,
                ).SerializeToString(),
            ).SerializeToString()
        )

        await test_core.wait_for_truthy(
            lambda: run_task is not None and run_task.cancelled()
        )


def get_request_id(requests: list[bytes]) -> str:
    for req in requests:
        try:
            msg = connect_pb2.ConnectMessage()
            msg.ParseFromString(req)
            if (
                msg.kind
                == connect_pb2.GatewayMessageType.GATEWAY_EXECUTOR_REQUEST
            ):
                req_data = connect_pb2.GatewayExecutorRequestData()
                req_data.ParseFromString(msg.payload)
                return req_data.request_id
        except Exception:
            pass
    return ""
