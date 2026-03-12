from __future__ import annotations

import asyncio

from inngest._internal import types

from . import connect_pb2
from .models import State


class BaseHandler:
    """
    Abstract base class that all Connect handlers inherit from.

    Provides:
        - Lifecycle management (start, close, closed)
        - Message handling interface (handle_msg)
        - Async event for coordinating shutdown (closed_event)
        - Deferred close: waits for pending requests to drain before closing

    Handler Lifecycle:
        1. start() - Called when the connection starts. Initialize resources here.
        2. handle_msg() - Called for every incoming WebSocket message.
        3. close() - Called to initiate graceful shutdown. Waits for
           pending_request_count to reach 0, runs after_close_drained(), then
           sets closed_event.
        4. closed() - Awaited to block until the handler has fully closed. This
           is a pure wait — do not put cleanup logic here.

    Subclass Hook:
        Override after_close_drained() to run cleanup (e.g. cancel and await
        tasks) after pending requests have drained but before the handler is
        marked as closed.

    Implementation Notes:
        - Subclasses should call super().__init__(state) in their __init__
        - Subclasses should call super().start() in their start()
        - The closed_event is lazily created on first access
        - Handlers should check closed_event.is_set() in loops to know when
          to stop
    """

    _closed_event: asyncio.Event | None = None
    _close_task: asyncio.Task[None] | None = None

    def __init__(self, logger: types.Logger, state: State) -> None:
        self._logger = logger
        self._state = state

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
        if self._close_task is not None:
            # Idempotency
            return

        async def _close_sequence() -> None:
            await self._state.pending_request_count.wait_for(0)
            try:
                await self.after_close_drained()
            except Exception as e:
                self._logger.error(
                    "Error during close sequence", extra={"error": str(e)}
                )
            if self._closed_event is not None:
                self._closed_event.set()

        self._close_task = asyncio.create_task(_close_sequence())

    async def after_close_drained(self) -> None:
        """
        Called after pending requests have drained but before the handler is
        marked as closed. Subclasses can override this to run arbitrary close
        logic that must happen after draining but before the handler is marked
        as closed.
        """

        pass

    async def closed(self) -> None:
        if self._closed_event is not None:
            await self._closed_event.wait()
