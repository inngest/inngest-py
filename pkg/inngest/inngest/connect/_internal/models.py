from __future__ import annotations

import dataclasses
import enum

import websockets

from . import connect_pb2
from .value_watcher import ValueWatcher


@dataclasses.dataclass
class State:
    """
    Shared state for the Connect feature.
    """

    conn_id: str | None
    conn_init: ValueWatcher[tuple[connect_pb2.AuthData, str] | None]
    conn_state: ValueWatcher[ConnectionState]
    exclude_gateways: list[str]
    extend_lease_interval: ValueWatcher[int | None]

    # Error that should make Connect close and raise an exception.
    fatal_error: ValueWatcher[Exception | None]

    init_handshake_complete: ValueWatcher[bool]

    # Number of pending requests. This is useful for handlers that need to wait
    # for all pending requests to complete before closing.
    pending_request_count: ValueWatcher[int]

    ws: ValueWatcher[websockets.ClientConnection | None]

    def allow_reconnect(self) -> bool:
        return self.conn_state.value not in [
            ConnectionState.CLOSED,
            ConnectionState.CLOSING,
        ]

    def close_ws(self) -> None:
        """
        Close the WebSocket connection
        """

        if self.allow_reconnect():
            self.conn_state.value = ConnectionState.RECONNECTING
        self.conn_init.value = None
        self.ws.value = None


class ConnectionState(enum.Enum):
    """
    State of the connection to the Inngest server.
    """

    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    CLOSING = "CLOSING"
    CONNECTING = "CONNECTING"
    PAUSED = "PAUSED"
    RECONNECTING = "RECONNECTING"
