"""Regression tests for inngest-py#380: close_ws() must reset
init_handshake_complete so a reconnecting heartbeat can't race the new
connection's init handshake (gateway closes with
connect_worker_hello_invalid_msg)."""

from inngest.connect._internal.models import ConnectionState, State
from inngest.connect._internal.value_watcher import ValueWatcher


def _make_state(conn_state: ConnectionState) -> State:
    return State(
        conn_id=ValueWatcher(None),
        conn_init=ValueWatcher(None),
        conn_state=ValueWatcher(conn_state),
        exclude_gateways=ValueWatcher([]),
        extend_lease_interval=ValueWatcher(None),
        fatal_error=ValueWatcher(None),
        init_handshake_complete=ValueWatcher(True),
        pending_request_count=ValueWatcher(0),
        ws=ValueWatcher(None),
    )


def test_close_ws_resets_init_handshake_complete_on_reconnect() -> None:
    state = _make_state(ConnectionState.ACTIVE)
    assert state.init_handshake_complete.value is True
    state.close_ws()
    assert state.conn_state.value is ConnectionState.RECONNECTING
    assert state.init_handshake_complete.value is False


def test_close_ws_resets_init_handshake_complete_on_close() -> None:
    state = _make_state(ConnectionState.CLOSED)
    state.close_ws()
    assert state.init_handshake_complete.value is False
