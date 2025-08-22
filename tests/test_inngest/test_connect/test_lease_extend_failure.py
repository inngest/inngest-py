# pyright: reportPrivateUsage=false

import asyncio
import typing

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
        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )
        event_name = test_core.random_suffix("event")
        state = test_core.BaseState()

        @client.create_function(
            fn_id="fn",
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> None:
            state.run_id = ctx.run_id
            await asyncio.sleep(5)

        conn = connect([(client, [fn])])
        task = asyncio.create_task(conn.start())
        self.addCleanup(conn.close, wait=True)
        self.addCleanup(task.cancel)

        await conn.wait_for_state(ConnectionState.ACTIVE)

        await client.send(inngest.Event(name=event_name))

        from inngest.connect._internal.execution_handler import (
            _ExecutionHandler,
        )
        from inngest.connect._internal.connection import (
            _WebSocketWorkerConnection,
        )

        ws_conn = typing.cast(_WebSocketWorkerConnection, conn)
        execution_handler: typing.Optional[_ExecutionHandler] = None  # pyright: ignore[reportUnknownVariableType]
        for handler in ws_conn._handlers:  # pyright: ignore[reportUnknownMemberType]
            if isinstance(handler, _ExecutionHandler):
                execution_handler = handler
                break
        assert execution_handler is not None

        await test_core.wait_for_len(
            lambda: list(execution_handler._pending_requests.values()),
            1,
        )
        request_id = next(iter(execution_handler._pending_requests.keys()))

        # Test successful lease extension
        success_ack = connect_pb2.ConnectMessage(
            kind=connect_pb2.GatewayMessageType.WORKER_REQUEST_EXTEND_LEASE_ACK,
            payload=connect_pb2.WorkerRequestExtendLeaseAckData(
                request_id=request_id,
                new_lease_id="new_lease_123",
            ).SerializeToString(),
        )

        execution_handler.handle_msg(
            success_ack, connect_pb2.AuthData(), "test_connection_id"
        )

        assert request_id in execution_handler._pending_requests
        assert (
            execution_handler._pending_requests[request_id][0].lease_id
            == "new_lease_123"
        )

        # Test failed lease extension
        failure_ack = connect_pb2.ConnectMessage(
            kind=connect_pb2.GatewayMessageType.WORKER_REQUEST_EXTEND_LEASE_ACK,
            payload=connect_pb2.WorkerRequestExtendLeaseAckData(
                request_id=request_id,
                new_lease_id=None,
            ).SerializeToString(),
        )

        execution_handler.handle_msg(
            failure_ack, connect_pb2.AuthData(), "test_connection_id"
        )

        assert request_id not in execution_handler._pending_requests
