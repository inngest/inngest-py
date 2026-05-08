import logging
import typing
import unittest

import websockets

from . import ws_utils
from .models import ConnectionState, State
from .value_watcher import ValueWatcher


class _FakeWS:
    def __init__(
        self,
        err: Exception | None = None,
        on_send: typing.Callable[[], None] | None = None,
    ) -> None:
        self._err = err
        self._on_send = on_send
        self.messages: list[bytes] = []

    async def send(self, message: bytes) -> None:
        self.messages.append(message)
        if self._on_send is not None:
            self._on_send()
        if self._err is not None:
            raise self._err


def _state(
    ws: websockets.ClientConnection | None,
    *,
    conn_state: ConnectionState = ConnectionState.ACTIVE,
) -> State:
    return State(
        conn_id=ValueWatcher(None),
        conn_init=ValueWatcher(None),
        conn_state=ValueWatcher(conn_state),
        exclude_gateways=ValueWatcher([]),
        extend_lease_interval=ValueWatcher(None),
        fatal_error=ValueWatcher(None),
        init_handshake_complete=ValueWatcher(True),
        pending_request_count=ValueWatcher(0),
        ws=ValueWatcher(ws),
    )


class TestSafeSend(unittest.IsolatedAsyncioTestCase):
    async def test_closes_current_ws_for_connection_fatal_error(self) -> None:
        ws = typing.cast(
            websockets.ClientConnection,
            _FakeWS(OSError("connection reset by peer")),
        )
        state = _state(ws)

        err = await ws_utils.safe_send(
            logging.getLogger(__name__), state, b"msg"
        )

        assert isinstance(err, OSError)
        assert state.ws.value is None
        assert state.conn_state.value == ConnectionState.RECONNECTING

    async def test_does_not_close_replacement_ws(self) -> None:
        replacement_ws = typing.cast(websockets.ClientConnection, _FakeWS())
        state = _state(None)

        stale_ws = typing.cast(
            websockets.ClientConnection,
            _FakeWS(
                OSError("connection reset by peer"),
                on_send=lambda: setattr(state.ws, "value", replacement_ws),
            ),
        )
        state.ws.value = stale_ws

        err = await ws_utils.safe_send(
            logging.getLogger(__name__), state, b"msg"
        )

        assert isinstance(err, OSError)
        assert state.ws.value is replacement_ws
        assert state.conn_state.value == ConnectionState.ACTIVE

    async def test_non_fatal_error_does_not_close_ws(self) -> None:
        ws = typing.cast(
            websockets.ClientConnection,
            _FakeWS(ValueError("bad message")),
        )
        state = _state(ws)

        err = await ws_utils.safe_send(
            logging.getLogger(__name__), state, b"msg"
        )

        assert isinstance(err, ValueError)
        assert state.ws.value is ws
        assert state.conn_state.value == ConnectionState.ACTIVE
