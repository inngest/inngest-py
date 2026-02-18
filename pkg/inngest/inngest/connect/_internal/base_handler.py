import asyncio

from inngest._internal import types

from . import connect_pb2


class BaseHandler:
    """
    Abstract base class that all Connect handlers inherit from.

    Provides:
        - Lifecycle management (start, close, closed)
        - Message handling interface (handle_msg)
        - Async event for coordinating shutdown (closed_event)

    Handler Lifecycle:
        1. start() - Called when the connection starts. Initialize resources here.
        2. handle_msg() - Called for every incoming WebSocket message.
        3. close() - Called to initiate graceful shutdown.
        4. closed() - Awaited to wait for complete shutdown.

    Implementation Notes:
        - Subclasses MUST call super().start() and super().close()
        - The closed_event is lazily created on first access
        - close() sets the closed_event; handlers should check
          closed_event.is_set() in loops to know when to stop
    """

    _closed_event: asyncio.Event | None = None

    @property
    def closed_event(self) -> asyncio.Event:
        if self._closed_event is None:
            self._closed_event = asyncio.Event()
        return self._closed_event

    def handle_msg(
        self,
        msg: connect_pb2.ConnectMessage,
        auth_data: connect_pb2.AuthData,
        connection_id: str,
    ) -> None:
        pass

    def start(self) -> types.MaybeError[None]:
        if self._closed_event is None:
            self._closed_event = asyncio.Event()
        return None

    def close(self) -> None:
        if self._closed_event is not None:
            self._closed_event.set()

    async def closed(self) -> None:
        if self._closed_event is not None:
            await self._closed_event.wait()
