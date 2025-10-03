import asyncio
import uuid

import websockets
import websockets.asyncio.connection
from inngest.connect._internal.consts import _protocol

from .net import get_available_port

_Connection = websockets.asyncio.connection.Connection


class WebSocketProxy:
    def __init__(
        self,
        server_uri: str,
    ):
        self._conns: dict[str, tuple[_Connection, _Connection]] = {}
        self._port = get_available_port()
        self._server_uri = server_uri
        self._server: websockets.Server | None = None
        self._tasks = set[asyncio.Task[None]]()
        self.forwarded_messages: list[bytes] = []

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

    async def send_to_clients(self, message: bytes) -> None:
        """
        Send a message to all connected clients (a.k.a. the SDKs).
        """

        for conn in self._conns.values():
            await conn[0].send(message)

    async def _handle_client(
        self,
        client_conn: websockets.ServerConnection,
    ) -> None:
        conn_id = str(uuid.uuid4())
        async with websockets.connect(
            self._server_uri,
            subprotocols=[_protocol],
        ) as server_conn:
            self._conns[conn_id] = (client_conn, server_conn)
            client_to_server = asyncio.create_task(
                self._forward_messages(client_conn, server_conn)
            )
            server_to_client = asyncio.create_task(
                self._forward_messages(server_conn, client_conn)
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
                del self._conns[conn_id]

    async def _forward_messages(
        self,
        source: _Connection,
        destination: _Connection,
    ) -> None:
        async for message in source:
            try:
                bmsg = message.encode() if isinstance(message, str) else message
                self.forwarded_messages.append(bmsg)

                await destination.send(message)
            except Exception as e:
                print("error sending message", e)

    async def abort_conns(self) -> None:
        """
        Abort connections at the transport level. This causes an abnormal
        websocket connection close (due to no close frame)
        """

        for conn in list(self._conns.values()):
            for c in conn:
                try:
                    c.transport.abort()
                except Exception:
                    pass
        self._conns.clear()

    async def send_invalid_frame(self) -> None:
        """
        Send invalid WebSocket frame data. This causes an abnormal websocket
        connection close
        """

        for conn in list(self._conns.values()):
            client_conn = conn[0]
            try:
                if hasattr(client_conn.transport, "write"):
                    # Invalid WebSocket frame (malformed header)
                    client_conn.transport.write(b"\x88\xff\x00\x00\x00\x00")
            except Exception:
                pass
        self._conns.clear()

    async def close_with_code(self) -> None:
        """
        Send close code 1000. This causes a normal websocket connection close
        """

        for conn in list(self._conns.values()):
            client_conn = conn[0]
            try:
                if hasattr(client_conn.transport, "write"):
                    # Close code 1000
                    client_conn.transport.write(b"\x88\x02\x03\xe8")
            except Exception:
                pass
        self._conns.clear()
