import asyncio

from inngest._internal import types

from . import connect_pb2


class _BaseHandler:
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
