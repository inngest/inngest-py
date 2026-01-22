import asyncio

from inngest._internal import types

from . import connect_pb2, ws_utils
from .base_handler import BaseHandler
from .consts import HEARTBEAT_INTERVAL_SEC
from .models import State


class HeartbeatHandler(BaseHandler):
    """
    Maintains connection health via periodic heartbeat messages.

    Responsibilities:
        1. Sending periodic WORKER_HEARTBEAT messages to the server
        2. Receiving GATEWAY_HEARTBEAT messages from the server

    The heartbeat interval is defined in consts.py (HEARTBEAT_INTERVAL_SEC).
    Heartbeats only begin after the initial handshake is complete.

    Graceful Shutdown:
        The heartbeat handler waits for all pending requests to complete before
        closing, ensuring heartbeats continue while work is in progress.
    """

    _heartbeat_sender_task: asyncio.Task[None] | None = None

    def __init__(
        self,
        logger: types.Logger,
        state: State,
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
        self._state.pending_request_count.on_value(0, super().close)

    async def closed(self) -> None:
        await super().closed()
        await self._state.pending_request_count.wait_for(0)

        if self._heartbeat_sender_task is not None:
            self._heartbeat_sender_task.cancel()
            try:
                await self._heartbeat_sender_task
            except asyncio.CancelledError:
                # This is expected since the task is likely calling
                # `asyncio.sleep` after cancellation.
                pass

    async def _heartbeat_sender(
        self,
    ) -> None:
        while self.closed_event.is_set() is False:
            # We can't send heartbeats until the handshake is complete. Doing so
            # isn't fatal, but will result in "connect_worker_hello_invalid_msg"
            # logs
            await self._state.init_handshake_complete.wait_for(True)

            # IMPORTANT: We need to get the WS conn each loop iteration because
            # it may have changed (e.g. due to a reconnect)
            ws = await self._state.ws.wait_for_not_none()

            self._logger.debug("Sending heartbeat")
            err = await ws_utils.safe_send(
                self._logger,
                self._state,
                ws,
                connect_pb2.ConnectMessage(
                    kind=connect_pb2.GatewayMessageType.WORKER_HEARTBEAT,
                ).SerializeToString(),
            )
            if err is not None:
                # Only log the error because we want to continue heartbeating
                self._logger.error(
                    "Error sending heartbeat", extra={"error": str(err)}
                )

            await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)

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
