import asyncio

from inngest._internal import types

from . import connect_pb2
from .base_handler import _BaseHandler
from .consts import _heartbeat_interval_sec
from .models import ConnectionState, _State


class _HeartbeatHandler(_BaseHandler):
    """
    Sends outgoing heartbeats to the Gateway and handles incoming heartbeat
    messages.
    """

    _heartbeat_sender_task: asyncio.Task[None] | None = None

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

        if self._heartbeat_sender_task is None:
            self._heartbeat_sender_task = asyncio.create_task(
                self._heartbeat_sender()
            )

        return None

    def close(self) -> None:
        super().close()

        if self._heartbeat_sender_task is not None:
            self._heartbeat_sender_task.cancel()

    async def closed(self) -> None:
        await super().closed()

        if self._heartbeat_sender_task is not None:
            try:
                await self._heartbeat_sender_task
            except asyncio.CancelledError:
                # This is expected since the task is likely calling
                # `asyncio.sleep` after cancellation.
                pass

    async def _heartbeat_sender(
        self,
    ) -> None:
        # Don't start heartbeats until the connection is established
        await self._state.ws.wait_for_not_none()

        while self.closed_event.is_set() is False:
            # Use try/except to ensure that we don't stop sending heartbeats if
            # one errors
            try:
                # Only send heartbeats when the connection is active.
                if self._state.conn_state.value != ConnectionState.ACTIVE:
                    await self._state.conn_state.wait_for(
                        ConnectionState.ACTIVE
                    )

                # IMPORTANT: We need to get the WS conn each loop iteration because
                # it may have changed (e.g. due to a reconnect)
                ws = await self._state.ws.wait_for_not_none()

                self._logger.debug("Sending heartbeat")
                await ws.send(
                    connect_pb2.ConnectMessage(
                        kind=connect_pb2.GatewayMessageType.WORKER_HEARTBEAT,
                    ).SerializeToString()
                )
            except Exception as e:
                # Don't raise the error because we want to continue heartbeating
                self._logger.error(
                    "Error sending heartbeat", extra={"error": str(e)}
                )
            await asyncio.sleep(_heartbeat_interval_sec)

        self._logger.debug("Heartbeater task stopped")

    def handle_msg(
        self,
        msg: connect_pb2.ConnectMessage,
        auth_data: connect_pb2.AuthData,
        connection_id: str,
    ) -> None:
        if msg.kind != connect_pb2.GatewayMessageType.GATEWAY_HEARTBEAT:
            return

        self._logger.debug("Received heartbeat")
