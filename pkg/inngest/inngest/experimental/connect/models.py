from __future__ import annotations

import dataclasses
import enum
import typing

import websockets

from . import connect_pb2
from .value_watcher import _ValueWatcher


@dataclasses.dataclass
class _State:
    conn_id: typing.Optional[str]
    conn_init: _ValueWatcher[typing.Optional[tuple[connect_pb2.AuthData, str]]]
    conn_state: _ValueWatcher[ConnectionState]
    draining: _ValueWatcher[bool]
    exclude_gateways: list[str]
    ws: _ValueWatcher[typing.Optional[websockets.ClientConnection]]


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
