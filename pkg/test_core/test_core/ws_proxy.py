import asyncio
import typing

import websockets
import websockets.asyncio.connection
from inngest.experimental.connect.consts import _protocol

from .net import get_available_port


class WebSocketProxy:
    def __init__(
        self,
        server_uri: str,
    ):
        self._port = get_available_port()
        self._server_uri = server_uri
        self._server: typing.Optional[websockets.Server] = None
        self._tasks = set[asyncio.Task[None]]()

    @property
    def url(self) -> str:
        return f"ws://0.0.0.0:{self._port}"

    async def start(self) -> None:
        self._server = await websockets.serve(
            self._handle_client,
            "0.0.0.0",
            self._port,
        )

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Cancel any active forwarding tasks.
        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _handle_client(
        self,
        server_conn: websockets.ServerConnection,
    ) -> None:
        await self._proxy(server_conn)

    async def _proxy(
        self,
        server_conn: websockets.ServerConnection,
    ) -> None:
        async with websockets.connect(
            self._server_uri,
            subprotocols=[_protocol],
        ) as client_conn:
            client_to_server = asyncio.create_task(
                self._forward_messages(server_conn, client_conn)
            )
            server_to_client = asyncio.create_task(
                self._forward_messages(client_conn, server_conn)
            )

            self._tasks.add(client_to_server)
            self._tasks.add(server_to_client)

            try:
                # Wait until either task completes (connection closes).
                done, pending = await asyncio.wait(
                    [client_to_server, server_to_client],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel the remaining task.
                for task in pending:
                    task.cancel()
            finally:
                # Remove tasks from the set.
                self._tasks.discard(client_to_server)
                self._tasks.discard(server_to_client)

    async def _forward_messages(
        self,
        source: websockets.asyncio.connection.Connection,
        destination: websockets.asyncio.connection.Connection,
    ) -> None:
        async for message in source:
            await destination.send(message)
