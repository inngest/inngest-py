"""
Internal-thread event loop for the Connect WebSocket connection.

Everything here runs on the dedicated Connect thread. The main thread
interacts only via ``loop.call_soon_threadsafe(worker.schedule_close)``.
"""

from __future__ import annotations

import asyncio
import typing

import websockets

from inngest._internal import types

from . import async_lib, connect_pb2
from .base_handler import BaseHandler
from .consts import (
    MAX_MESSAGE_SIZE,
    POST_CONNECT_SETTLE_SEC,
    PROTOCOL,
    RECONNECTION_DELAY_SEC,
)
from .errors import UnreachableError
from .models import ConnectionState, State
from .value_watcher import ValueWatcher


class IsolatedWorker:
    """
    Encapsulates everything running in the internal thread.
    """

    # True when we start closing. This prevents the finally block in `run()`
    # from double-closing.
    _closing: bool = False

    # Prevents the event loop from going idle, which would delay shutdown.
    _event_loop_keep_alive_task: asyncio.Task[None] | None = None

    # Background task that reads and dispatches incoming WS messages.
    _message_handler_task: asyncio.Task[types.MaybeError[None]] | None = None

    def __init__(
        self,
        handlers: list[BaseHandler],
        state: State,
        logger: types.Logger,
        handling_message_count: ValueWatcher[int],
    ) -> None:
        self._handlers = handlers
        self._state = state
        self._logger = logger
        self._handling_message_count = handling_message_count

        # Strong refs to fire-and-forget tasks so they aren't GC'd.
        self._background_tasks: set[asyncio.Task[typing.Any]] = set()

    async def run(self) -> None:
        """Reconnect loop: connects, reads messages, reconnects on failure."""

        self._event_loop_keep_alive_task = _event_loop_keep_alive()

        for h in self._handlers:
            err = h.start()
            if isinstance(err, Exception):
                raise err

        try:
            while self._state.allow_reconnect():
                gateway_endpoint = await _wait_for_gateway_endpoint(self._state)
                if isinstance(gateway_endpoint, Exception):
                    # Fatal error.
                    raise gateway_endpoint
                endpoint, closing = gateway_endpoint
                if closing:
                    return

                try:
                    self._logger.debug(
                        "Gateway connecting",
                        extra={"endpoint": endpoint},
                    )

                    async with websockets.connect(
                        endpoint,
                        max_size=MAX_MESSAGE_SIZE,
                        subprotocols=[PROTOCOL],
                    ) as ws:
                        self._logger.debug("Gateway connected")
                        self._state.ws.value = ws
                        self._message_handler_task = asyncio.create_task(
                            self._handle_msg(ws)
                        )

                        await self._state.conn_init.wait_for_change()
                        await asyncio.sleep(POST_CONNECT_SETTLE_SEC)
                except Exception as e:
                    self._logger.error(
                        f"Gateway connection error: {e}. Reconnecting..."
                    )
                    self._state.close_ws()
                    await asyncio.sleep(RECONNECTION_DELAY_SEC)
                except asyncio.CancelledError:
                    self._logger.debug("Gateway connection cancelled")
                    break
                finally:
                    # WS is closed; wait for the message handler to finish.
                    if self._message_handler_task is not None:
                        await self._message_handler_task
                        self._message_handler_task = None
                    self._logger.debug("Gateway connection closed")
        finally:
            if not self._closing:
                for h in self._handlers:
                    h.close()
            await self._wait_for_handlers_closed()
            self._state.conn_state.value = ConnectionState.CLOSED
            self._state.close_ws()
            await async_lib.cancel_and_wait(self._event_loop_keep_alive_task)

    async def _handle_msg(
        self,
        ws: websockets.ClientConnection,
    ) -> types.MaybeError[None]:
        """Read messages from the WS and dispatch to all handlers."""

        disconnect = False
        try:
            async for raw_msg in ws:
                if self._state.conn_init.value is None:
                    return UnreachableError("Missing conn init")

                if not isinstance(raw_msg, bytes):
                    self._logger.debug(
                        "Received non-bytes message", extra={"message": raw_msg}
                    )
                    continue

                msg = connect_pb2.ConnectMessage()
                msg.ParseFromString(raw_msg)
                self._logger.debug(
                    "Received message",
                    extra={
                        "kind": connect_pb2.GatewayMessageType.Name(msg.kind),
                        "payload": msg.payload,
                    },
                )

                conn_id = self._state.conn_id
                if conn_id is None:
                    return UnreachableError("Missing connection ID")

                self._handling_message_count.value += 1
                try:
                    for h in self._handlers:
                        h.handle_msg(
                            msg,
                            self._state.conn_init.value[0],
                            conn_id,
                        )
                finally:
                    self._handling_message_count.value -= 1

            if ws.close_code is not None:
                # Normal connection close
                self._logger.debug(
                    "Connection closed",
                    extra={
                        "close_code": ws.close_code,
                        "close_reason": ws.close_reason,
                    },
                )
                disconnect = True
        except websockets.exceptions.ConnectionClosedError as e:
            self._logger.debug(
                "Connection closed abnormally", extra={"error": str(e)}
            )
            disconnect = True
        except websockets.exceptions.ConnectionClosedOK:
            self._logger.debug("Connection closed normally")
            disconnect = True
        except Exception as e:
            self._logger.debug("Connection error", extra={"error": str(e)})
            disconnect = True

        if disconnect is True:
            self._state.close_ws()
        return None

    def schedule_close(self) -> None:
        """
        Called via call_soon_threadsafe from the main thread. Does not block.
        """

        task = asyncio.create_task(self._close())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _close(self) -> None:
        """
        Send WORKER_PAUSE, close handlers, wait for in-flight work.
        """

        ws = self._state.ws.value
        if ws is not None:
            try:
                # Send WORKER_PAUSE to the Inngest Server, telling it to stop
                # sending execution requests.
                await ws.send(
                    connect_pb2.ConnectMessage(
                        kind=connect_pb2.GatewayMessageType.WORKER_PAUSE,
                    ).SerializeToString()
                )
            except Exception as e:
                self._logger.error(
                    "Failed to send WORKER_PAUSE",
                    extra={"error": str(e)},
                )
        else:
            self._logger.warning(
                "Unable to send worker pause message because the WebSocket connection is not open"
            )

        # Close handlers (stop accepting new work) and wait for pending work
        # to finish before unblocking the reconnect loop. This ensures the WS
        # stays open long enough for in-flight function results to be sent.
        self._closing = True
        for h in self._handlers:
            h.close()
        await self._wait_for_handlers_closed()

    async def _wait_for_handlers_closed(self) -> None:
        """
        Block until all handlers are closed and no messages are in-flight.
        """

        await asyncio.gather(*[h.closed() for h in self._handlers])
        await self._handling_message_count.wait_for(0)
        self._state.conn_init.value = None


def _event_loop_keep_alive() -> asyncio.Task[None]:
    """
    Create a task whose sole purpose is to keep the event loop alive. Without
    this, the event loop can go into an idle mode. This isn't a huge deal, but
    it can make graceful shutdown take ~5 seconds longer.
    """

    async def _keep_alive() -> None:
        while True:  # noqa: ASYNC110
            await asyncio.sleep(1)

    return asyncio.create_task(_keep_alive())


async def _wait_for_gateway_endpoint(
    state: State,
) -> types.MaybeError[tuple[str, bool]]:
    """
    Wait for the Gateway endpoint to be set or for the connection to be closing.
    Returns the Gateway endpoint and a boolean indicating if the connection is
    closing.
    """

    done_tasks, pending_tasks = await asyncio.wait(
        (
            asyncio.create_task(state.conn_init.wait_for_not_none()),
            asyncio.create_task(
                state.conn_state.wait_for(ConnectionState.CLOSING)
            ),
            asyncio.create_task(state.fatal_error.wait_for_not_none()),
        ),
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Kill the losers
    for t in pending_tasks:
        t.cancel()

    for t in done_tasks:
        # Need to cast because Mypy doesn't understand the type (it thinks it's
        # `object`).
        r = typing.cast(
            ConnectionState | tuple[connect_pb2.AuthData, str] | Exception,
            t.result(),
        )

        if r is ConnectionState.CLOSING:
            # We need to shutdown.
            return ("", True)
        if isinstance(r, Exception):
            return r
        if isinstance(r, ConnectionState):
            return UnreachableError(
                "We already checked the only possible ConnectionState"
            )

        return r[1], False

    return UnreachableError()
