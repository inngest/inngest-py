import asyncio
import typing

import websockets

from inngest._internal import types

from . import connect_pb2
from .base_handler import _BaseHandler
from .consts import _heartbeat_interval_sec
from .errors import _UnreachableError
from .models import ConnectionState, _State


class _HeartbeatHandler(_BaseHandler):
    """
    Sends outgoing heartbeats to the Gateway and handles incoming heartbeat
    messages.
    """

    _heartbeat_sender_task: typing.Optional[asyncio.Task[None]] = None

    def __init__(
        self,
        logger: types.Logger,
        state: _State,
    ) -> None:
        self._logger = logger
        self._state = state

    def start(self) -> types.MaybeError[None]:
        err = super().start()
        if err is not None:
            return err

        if self._state.ws is None:
            return _UnreachableError("missing websocket")

        if self._heartbeat_sender_task is None:
            self._heartbeat_sender_task = asyncio.create_task(
                self._heartbeat_sender(self._state.ws)
            )

        return None

    def close(self) -> None:
        super().close()

        if self._heartbeat_sender_task is not None:
            self._heartbeat_sender_task.cancel()

    async def closed(self) -> None:
        if self._heartbeat_sender_task is not None:
            try:
                await self._heartbeat_sender_task
            except asyncio.CancelledError:
                # This is expected since the task is likely calling
                # `asyncio.sleep` after cancellation.
                pass

    async def _heartbeat_sender(
        self,
        ws: websockets.ClientConnection,
    ) -> None:
        while self.closed_event.is_set() is False:
            # Only send heartbeats when the connection is active.
            if self._state.conn_state.value != ConnectionState.ACTIVE:
                await self._state.conn_state.wait_for(ConnectionState.ACTIVE)

            self._logger.debug("Sending heartbeat")
            await ws.send(
                connect_pb2.ConnectMessage(
                    kind=connect_pb2.GatewayMessageType.WORKER_HEARTBEAT,
                ).SerializeToString()
            )

            await asyncio.sleep(_heartbeat_interval_sec)

    def handle_msg(
        self,
        msg: connect_pb2.ConnectMessage,
        auth_data: connect_pb2.AuthData,
        connection_id: str,
    ) -> None:
        if msg.kind != connect_pb2.GatewayMessageType.GATEWAY_HEARTBEAT:
            return

        self._logger.debug("Received heartbeat")
