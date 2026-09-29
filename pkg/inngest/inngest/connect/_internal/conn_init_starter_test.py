import datetime
import unittest
import unittest.mock

import httpx
import test_core

from inngest._internal import net

from . import connect_pb2
from .conn_init_starter import ConnInitHandler, validate_gateway_endpoint
from .models import ConnectionState, State
from .value_watcher import ValueWatcher


def _new_state() -> State:
    return State(
        conn_id=ValueWatcher(None),
        conn_init=ValueWatcher(None),
        conn_state=ValueWatcher(ConnectionState.CONNECTING),
        exclude_gateways=ValueWatcher([]),
        extend_lease_interval=ValueWatcher(None),
        fatal_error=ValueWatcher(None),
        init_handshake_complete=ValueWatcher(False),
        pending_request_count=ValueWatcher(0),
        ws=ValueWatcher(None),
    )


def _new_handler(state: State) -> ConnInitHandler:
    return ConnInitHandler(
        api_origin="http://localhost:1",
        env=None,
        http_client=unittest.mock.Mock(),
        http_client_sync=unittest.mock.Mock(),
        logger=unittest.mock.Mock(),
        rewrite_gateway_endpoint=None,
        signing_key=None,
        signing_key_fallback=None,
        state=state,
    )


class TestConnInitHandler(unittest.IsolatedAsyncioTestCase):
    async def test_retries_until_server_recovers(self) -> None:
        """
        A prolonged outage of /v0/connect/start must not be fatal. The handler
        keeps retrying and connects once the server is back.
        """

        outage_attempts = 8
        calls = 0

        async def fake_fetch(
            *args: object, **kwargs: object
        ) -> httpx.Response | Exception:
            nonlocal calls
            calls += 1
            if calls <= outage_attempts:
                return httpx.Response(503)
            return httpx.Response(
                200,
                content=connect_pb2.StartResponse(
                    connection_id="conn-1",
                    gateway_endpoint="ws://localhost:1234",
                    session_token="session",
                    sync_token="sync",
                ).SerializeToString(),
            )

        state = _new_state()
        handler = _new_handler(state)

        with (
            unittest.mock.patch.object(
                net, "fetch_with_auth_fallback", fake_fetch
            ),
            unittest.mock.patch(
                "inngest.connect._internal.conn_init_starter.CONN_INIT_RETRY_INTERVAL_SEC",
                0,
            ),
        ):
            handler.start()

            def assertion() -> None:
                assert state.fatal_error.value is None
                assert state.conn_init.value is not None
                assert state.conn_init.value[1] == "ws://localhost:1234"

            await test_core.wait_for(
                assertion, timeout=datetime.timedelta(seconds=10)
            )

            handler.close()
            await handler.closed()
        assert calls == outage_attempts + 1

    async def test_unauthorized_is_fatal(self) -> None:
        async def fake_fetch(
            *args: object, **kwargs: object
        ) -> httpx.Response | Exception:
            return httpx.Response(401)

        state = _new_state()
        handler = _new_handler(state)

        with (
            unittest.mock.patch.object(
                net, "fetch_with_auth_fallback", fake_fetch
            ),
            unittest.mock.patch(
                "inngest.connect._internal.conn_init_starter.CONN_INIT_RETRY_INTERVAL_SEC",
                0,
            ),
        ):
            handler.start()

            def assertion() -> None:
                assert isinstance(state.fatal_error.value, Exception)

            await test_core.wait_for(
                assertion, timeout=datetime.timedelta(seconds=10)
            )

            handler.close()
            await handler.closed()


class Test_validate_gateway_endpoint(unittest.TestCase):
    def test_valid(self) -> None:
        assert validate_gateway_endpoint("ws://example.com") is None
        assert validate_gateway_endpoint("wss://example.com") is None

    def test_invalid(self) -> None:
        # Unsupported scheme
        err = validate_gateway_endpoint("http://example.com")
        assert isinstance(err, Exception)
        assert (
            str(err)
            == "gateway endpoint scheme http is not valid, must be one of ws, wss"
        )

        # Missing hostname
        err = validate_gateway_endpoint("ws://")
        assert isinstance(err, Exception)
        assert str(err) == "gateway endpoint hostname is required"

        # Empty (use spaces to also test stripping)
        err = validate_gateway_endpoint("  ")
        assert isinstance(err, Exception)
        assert str(err) == "gateway endpoint is empty"
