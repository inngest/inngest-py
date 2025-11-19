import asyncio

from inngest._internal import types

from . import connect_pb2
from .base_handler import _BaseHandler
from .models import _State


class _DrainHandler(_BaseHandler):
    _closed_event: asyncio.Event | None = None

    def __init__(
        self,
        logger: types.Logger,
        state: _State,
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
