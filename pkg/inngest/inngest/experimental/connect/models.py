from __future__ import annotations

import asyncio
import dataclasses
import enum
import typing

import websockets

from inngest._internal import types

from . import connect_pb2


class _Handler(typing.Protocol):
    def handle_msg(
        self,
        msg: connect_pb2.ConnectMessage,
        auth_data: connect_pb2.AuthData,
        connection_id: str,
    ) -> None: ...

    def start(
        self,
        ws: websockets.ClientConnection,
    ) -> types.MaybeError[None]: ...

    def close(self) -> None: ...

    async def closed(self) -> None: ...


@dataclasses.dataclass
class _State:
    auth_data: typing.Optional[connect_pb2.AuthData]
    conn_id: typing.Optional[str]
    conn_state: _ValueWatcher[ConnectionState]
    exclude_gateways: list[str]
    gateway_url: typing.Optional[str]


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


T = typing.TypeVar("T")


class _ValueWatcher(typing.Generic[T]):
    """
    A container that allows consumers to watch for changes.
    """

    _event: typing.Optional[asyncio.Event] = None

    def __init__(
        self,
        initial_value: T,
        *,
        on_change: typing.Optional[typing.Callable[[T, T], None]] = None,
    ) -> None:
        """
        Args:
            initial_value: The initial value.
            on_change: Called when the value changes. Good for debug logging.
        """

        self._on_change = on_change
        self._value = initial_value

    @property
    def value(self) -> T:
        return self._value

    @value.setter
    def value(self, new_value: T) -> None:
        if self._event is None:
            self._event = asyncio.Event()

        if new_value != self._value:
            old_value = self._value
            self._value = new_value
            self._event.set()
            if self._on_change:
                self._on_change(old_value, new_value)

    async def wait_for(self, value: T) -> None:
        async for state in self.watch():
            if state == value:
                return

    async def watch(self) -> typing.AsyncGenerator[T, None]:
        """
        Watch the value for changes.
        """

        if self._event is None:
            self._event = asyncio.Event()

        while True:
            # Wait for the value to change.
            await self._event.wait()
            self._event.clear()

            # Yield the new value.
            yield self._value
