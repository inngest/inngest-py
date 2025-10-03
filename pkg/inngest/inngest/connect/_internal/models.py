from __future__ import annotations

import dataclasses
import enum

import websockets

from . import connect_pb2
from .value_watcher import _ValueWatcher


@dataclasses.dataclass
class _State:
    conn_id: str | None
    conn_init: _ValueWatcher[tuple[connect_pb2.AuthData, str] | None]
    conn_state: _ValueWatcher[ConnectionState]
    exclude_gateways: list[str]
    extend_lease_interval: _ValueWatcher[int | None]

    # Error that should make Connect close and raise an exception.
    fatal_error: _ValueWatcher[Exception | None]

    ws: _ValueWatcher[websockets.ClientConnection | None]


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
