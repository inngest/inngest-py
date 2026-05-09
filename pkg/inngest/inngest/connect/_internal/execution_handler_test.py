import logging
import typing
import unittest

import httpx
import websockets

from inngest._internal import comm_lib, net

from . import connect_pb2
from .execution_handler import ExecutionHandler
from .models import ConnectionState, State
from .value_watcher import ValueWatcher


class _FakeWS:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    async def send(self, message: bytes) -> None:
        self.sent.append(message)


class _FakeState(State):
    def __init__(self, ws: _FakeWS) -> None:
        super().__init__(
            conn_id=ValueWatcher(None),
            conn_init=ValueWatcher(None),
            conn_state=ValueWatcher(ConnectionState.ACTIVE),
            exclude_gateways=ValueWatcher([]),
            extend_lease_interval=ValueWatcher(1),
            fatal_error=ValueWatcher(None),
            init_handshake_complete=ValueWatcher(True),
            pending_request_count=ValueWatcher(0),
            ws=ValueWatcher(typing.cast(websockets.ClientConnection, ws)),
        )


class _FakeExecutionHandler(ExecutionHandler):
    def __init__(self, ws: _FakeWS | None = None) -> None:
        super().__init__(
            api_origin="http://127.0.0.1",
            comm_handlers={},
            http_client=typing.cast(net.ThreadAwareAsyncHTTPClient, object()),
            http_client_sync=typing.cast(httpx.Client, object()),
            logger=logging.getLogger(__name__),
            signing_key=None,
            signing_key_fallback=None,
            state=_FakeState(ws or _FakeWS()),
        )


class TestExecutionHandler(unittest.IsolatedAsyncioTestCase):
    async def test_ack_failure_abandons_request_without_error_reply(
        self,
    ) -> None:
        """
        If there's an error when sending the execution request ack, then we
        don't process the execution request and we don't buffer.
        """

        class WS(_FakeWS):
            async def send(self, message: bytes) -> None:
                await super().send(message)
                raise OSError("connection reset by peer")

        ws = WS()
        handler = _FakeExecutionHandler(ws)

        class CommHandler:
            called = False

            async def post(
                self,
                req: comm_lib.CommRequest,
            ) -> comm_lib.CommResponse:
                print("yo")
                self.called = True
                raise Exception("unreachable")

        comm_handler = CommHandler()
        req_data = connect_pb2.GatewayExecutorRequestData(
            account_id="account",
            app_id="app",
            env_id="env",
            function_slug="fn",
            request_id="req",
        )

        await handler._execute_request(
            req_data,
            typing.cast(comm_lib.CommHandler, comm_handler),
        )

        # We attempted to send the execution request ack
        assert len(ws.sent) == 1
        msg = connect_pb2.ConnectMessage()
        msg.ParseFromString(ws.sent[0])
        assert msg.kind == connect_pb2.GatewayMessageType.WORKER_REQUEST_ACK

        # CommHandler was not called since the ack failed to send
        assert comm_handler.called is False

        # Nothing buffered
        assert handler._buffer.length() == 0

    async def test_failed_flush_keeps_message_for_retry(self) -> None:
        """
        If a message flush fails then the buffer retains the message.
        """

        class Handler(_FakeExecutionHandler):
            async def _flush_message(self, msg: bytes) -> Exception | None:
                return Exception("temporary failure")

        handler = Handler()
        handler._buffer.add("req", b"reply")

        await handler._flush_ready_messages(0)

        assert handler._buffer.get("req") == b"reply"

    async def test_successful_flush_deletes_message(self) -> None:
        """
        If a message flush succeeds then the buffer deletes the message.
        """

        class Handler(_FakeExecutionHandler):
            async def _flush_message(self, msg: bytes) -> Exception | None:
                return None

        handler = Handler()

        handler._buffer.add("req", b"reply")

        await handler._flush_ready_messages(0)

        assert handler._buffer.get("req") is None
