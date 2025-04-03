import asyncio
import typing

from inngest._internal import types

from . import connect_pb2
from .models import _State


class _DrainHandler:
    _closed_event: typing.Optional[asyncio.Event] = None

    def __init__(
        self,
        logger: types.Logger,
        state: _State,
    ) -> None:
        self._logger = logger
        self._state = state

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

    def handle_msg(
        self,
        msg: connect_pb2.ConnectMessage,
        auth_data: connect_pb2.AuthData,
        connection_id: str,
    ) -> None:
        if msg.kind != connect_pb2.GatewayMessageType.GATEWAY_CLOSING:
            return

        self._logger.debug("Draining")
        self._state.draining.value = True
