import logging
import typing
import unittest
from unittest import mock

import httpx
import websockets

from inngest._internal import comm_lib, net

from . import connect_pb2
from . import ws_utils as ws_utils_module
from .execution_handler import ExecutionHandler
from .models import ConnectionState, State
from .value_watcher import ValueWatcher


class _FakeCommHandler:
    called = False

    async def post(
        self,
        req: comm_lib.CommRequest,
    ) -> comm_lib.CommResponse:
        self.called = True
        raise AssertionError("post should not be called")


class _FakeWS:
    async def send(self, message: bytes) -> None:
        pass


class _TestExecutionHandler(ExecutionHandler):
    flush_results: list[Exception | None]

    async def _flush_message(self, msg: bytes) -> Exception | None:
        return self.flush_results.pop(0)


def _state() -> State:
    return State(
        conn_id=ValueWatcher(None),
        conn_init=ValueWatcher(None),
        conn_state=ValueWatcher(ConnectionState.ACTIVE),
        exclude_gateways=ValueWatcher([]),
        extend_lease_interval=ValueWatcher(1),
        fatal_error=ValueWatcher(None),
        init_handshake_complete=ValueWatcher(True),
        pending_request_count=ValueWatcher(0),
        ws=ValueWatcher(typing.cast(websockets.ClientConnection, _FakeWS())),
    )


def _handler() -> _TestExecutionHandler:
    handler = _TestExecutionHandler(
        api_origin="http://127.0.0.1",
        comm_handlers={},
        http_client=typing.cast(net.ThreadAwareAsyncHTTPClient, object()),
        http_client_sync=typing.cast(httpx.Client, object()),
        logger=logging.getLogger(__name__),
        signing_key=None,
        signing_key_fallback=None,
        state=_state(),
    )
    handler.flush_results = []
    return handler


class TestExecutionHandler(unittest.IsolatedAsyncioTestCase):
    async def test_ack_failure_abandons_request_without_error_reply(
        self,
    ) -> None:
        handler = _handler()
        comm_handler = _FakeCommHandler()
        req_data = connect_pb2.GatewayExecutorRequestData(
            account_id="account",
            app_id="app",
            env_id="env",
            function_slug="fn",
            request_id="req",
        )
        send_calls: list[bytes] = []

        async def fail_ack(
            logger: object,
            state: State,
            message: bytes,
        ) -> Exception | None:
            send_calls.append(message)
            return OSError("connection reset by peer")

        with mock.patch.object(
            ws_utils_module,
            "safe_send",
            fail_ack,
        ):
            await handler._execute_request(
                req_data,
                typing.cast(comm_lib.CommHandler, comm_handler),
            )

        assert len(send_calls) == 1
        assert comm_handler.called is False
        assert handler._buffer.get(req_data.request_id) is None

    async def test_failed_flush_keeps_message_for_retry(self) -> None:
        handler = _handler()
        handler.flush_results = [Exception("temporary failure")]
        handler._buffer.add("req", b"reply")

        await handler._flush_ready_messages(0)

        assert handler._buffer.get("req") == b"reply"

    async def test_successful_flush_deletes_message(self) -> None:
        handler = _handler()
        handler.flush_results = [None]
        handler._buffer.add("req", b"reply")

        await handler._flush_ready_messages(0)

        assert handler._buffer.get("req") is None
