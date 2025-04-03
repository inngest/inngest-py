from __future__ import annotations

import dataclasses
import enum
import typing

import websockets

from inngest._internal import types

from . import connect_pb2
from .value_watcher import _ValueWatcher


class _Handler(typing.Protocol):
    def handle_msg(
        self,
        msg: connect_pb2.ConnectMessage,
        auth_data: connect_pb2.AuthData,
        connection_id: str,
    ) -> None: ...

    def start(self) -> types.MaybeError[None]: ...

    def close(self) -> None: ...

    async def closed(self) -> None: ...


@dataclasses.dataclass
class _State:
    conn_id: typing.Optional[str]
    conn_init: _ValueWatcher[typing.Optional[tuple[connect_pb2.AuthData, str]]]
    conn_state: _ValueWatcher[ConnectionState]
    draining: _ValueWatcher[bool]
    exclude_gateways: list[str]
    ws: typing.Optional[websockets.ClientConnection]


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
