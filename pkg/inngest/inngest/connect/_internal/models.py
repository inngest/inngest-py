from __future__ import annotations

import dataclasses
import enum
import threading

import websockets

from . import connect_pb2
from .value_watcher import ValueWatcher


@dataclasses.dataclass
class State:
    """
    Shared state for Connect.
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

    # Lock for non-_ValueWatcher attributes (conn_id, exclude_gateways)
    _lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)

    def get_conn_id(self) -> str | None:
        """Thread-safe getter for conn_id."""
        with self._lock:
            return self.conn_id

    def set_conn_id(self, conn_id: str | None) -> None:
        """Thread-safe setter for conn_id."""
        with self._lock:
            self.conn_id = conn_id

    def get_exclude_gateways(self) -> list[str]:
        """Thread-safe getter for exclude_gateways (returns a copy)."""
        with self._lock:
            return list(self.exclude_gateways)

    def add_exclude_gateway(self, gateway: str) -> None:
        """Thread-safe method to add a gateway to exclude list."""
        with self._lock:
            if gateway not in self.exclude_gateways:
                self.exclude_gateways.append(gateway)

    def clear_exclude_gateways(self) -> None:
        """Thread-safe method to clear the exclude gateways list."""
        with self._lock:
            self.exclude_gateways.clear()

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
