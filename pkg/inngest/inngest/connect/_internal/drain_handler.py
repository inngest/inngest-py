import asyncio

from inngest._internal import types

from . import connect_pb2
from .base_handler import BaseHandler
from .models import State


class DrainHandler(BaseHandler):
    """
    Handles the GATEWAY_CLOSING message for graceful gateway shutdown.

    The server sends GATEWAY_CLOSING when the gateway is shutting down (e.g.
    Inngest is doing a deploy on their end).

    When GATEWAY_CLOSING is received:
        1. The WebSocket connection is cleared via state.close_ws()
        2. This triggers the reconnection logic elsewhere
        3. The SDK connects to a different gateway

    This allows the server to gracefully drain connections without
    interrupting in-flight work.
    """

    _closed_event: asyncio.Event | None = None

    def __init__(
        self,
        logger: types.Logger,
        state: State,
    ) -> None:
        self._logger = logger
        self._state = state

    def handle_msg(
        self,
        msg: connect_pb2.ConnectMessage,
        auth_data: connect_pb2.AuthData,
        connection_id: str,
    ) -> None:
        if msg.kind != connect_pb2.GatewayMessageType.GATEWAY_CLOSING:
            return

        self._logger.debug("Draining")

        # Clear the connection to trigger reconnection logic elsewhere
        self._state.close_ws()
