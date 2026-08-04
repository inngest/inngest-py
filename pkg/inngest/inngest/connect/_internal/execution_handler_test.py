# pyright: reportPrivateUsage=false

import asyncio
import unittest
import unittest.mock

from . import connect_pb2
from .execution_handler import ExecutionHandler
from .models import ConnectionState, State
from .value_watcher import ValueWatcher


class TestExecutionHandlerLeaseExtendAck(unittest.IsolatedAsyncioTestCase):
    def _handler(self) -> ExecutionHandler:
        state = State(
            conn_id=ValueWatcher(None),
            conn_init=ValueWatcher(None),
            conn_state=ValueWatcher(ConnectionState.ACTIVE),
            exclude_gateways=ValueWatcher([]),
            extend_lease_interval=ValueWatcher(None),
            fatal_error=ValueWatcher(None),
            init_handshake_complete=ValueWatcher(True),
            pending_request_count=ValueWatcher(0),
            ws=ValueWatcher(None),
        )
        return ExecutionHandler(
            api_origin="http://127.0.0.1",
            comm_handlers={},
            http_client=unittest.mock.Mock(),
            http_client_sync=unittest.mock.Mock(),
            logger=unittest.mock.Mock(),
            signing_key=None,
            signing_key_fallback=None,
            state=state,
        )

    def _ack(
        self, request_id: str, new_lease_id: str | None
    ) -> connect_pb2.ConnectMessage:
        kwargs: dict[str, str | None] = {"request_id": request_id}
        if new_lease_id is not None:
            kwargs["new_lease_id"] = new_lease_id
        return connect_pb2.ConnectMessage(
            kind=connect_pb2.GatewayMessageType.WORKER_REQUEST_EXTEND_LEASE_ACK,
            payload=connect_pb2.WorkerRequestExtendLeaseAckData(
                **kwargs
            ).SerializeToString(),
        )

    async def test_late_ack_for_unknown_request_does_not_add_pending_request(
        self,
    ) -> None:
        handler = self._handler()

        handler._handle_lease_extend_ack(self._ack("req-1", "late-lease"))

        self.assertEqual(handler._pending_requests.count(), 0)
        self.assertEqual(handler._state.pending_request_count.value, 0)

    async def test_ack_updates_existing_request_lease(self) -> None:
        handler = self._handler()
        task = asyncio.create_task(asyncio.sleep(60))
        self.addAsyncCleanup(_cancel_task, task)
        req = connect_pb2.GatewayExecutorRequestData(
            request_id="req-1",
            lease_id="lease-1",
        )
        handler._pending_requests.add("req-1", req, task)

        handler._handle_lease_extend_ack(self._ack("req-1", "lease-2"))

        self.assertEqual(req.lease_id, "lease-2")
        self.assertEqual(handler._pending_requests.count(), 1)
        self.assertEqual(handler._state.pending_request_count.value, 1)

    async def test_lease_loss_ack_keeps_execution_pending(self) -> None:
        handler = self._handler()
        task = asyncio.create_task(asyncio.sleep(60))
        self.addAsyncCleanup(_cancel_task, task)
        req = connect_pb2.GatewayExecutorRequestData(
            request_id="req-1",
            lease_id="lease-1",
        )
        handler._pending_requests.add("req-1", req, task)
        task.add_done_callback(lambda _: handler._finish_request("req-1"))

        handler._handle_lease_extend_ack(self._ack("req-1", None))
        await asyncio.sleep(0)

        self.assertFalse(task.cancelled())
        self.assertEqual(handler._pending_requests.count(), 1)
        self.assertEqual(handler._state.pending_request_count.value, 1)
        self.assertIn("req-1", handler._lease_extension_stopped)

        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

        self.assertEqual(handler._pending_requests.count(), 0)
        self.assertEqual(handler._state.pending_request_count.value, 0)
        self.assertNotIn("req-1", handler._lease_extension_stopped)


async def _cancel_task(task: asyncio.Task[object]) -> None:
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
