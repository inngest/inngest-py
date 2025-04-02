from __future__ import annotations

import asyncio
import socket
import typing

import httpx
import websockets

import inngest
from inngest._internal import comm_lib, net, server_lib, types

from . import connect_pb2
from .conn_starter import _ConnStarter
from .consts import (
    _default_shutdown_signals,
    _framework,
    _protocol,
)
from .errors import _UnreachableError
from .execution_handler import _ExecutionHandler
from .heartbeat_handler import _HeartbeatHandler
from .init_handler import _InitHandler
from .models import ConnectionState, _Handler, _State
from .value_watcher import _ValueWatcher


class WorkerConnection(typing.Protocol):
    """
    Connection between the SDK and Inngest server.
    """

    async def close(self, *, wait: bool = False) -> None:
        """
        Wait for the connection to be closed.

        Args:
        ----
            wait: If True, wait for the connection to finish closing.
        """
        ...

    async def closed(self) -> None:
        """
        Wait for the connection to finish closing.
        """
        ...

    def get_connection_id(self) -> str:
        """
        Get the connection ID.
        """
        ...

    def get_state(self) -> ConnectionState:
        """
        Get the connection state.
        """
        ...

    async def start(self) -> None:
        """
        Start the connection.
        """
        ...

    async def wait_for_state(self, state: ConnectionState) -> None:
        """
        Wait for the connection to reach a specific state.
        """
        ...


class _WebSocketWorkerConnection(WorkerConnection):
    _closed_event: typing.Optional[asyncio.Event] = None
    _message_handler_task: typing.Optional[
        asyncio.Task[types.MaybeError[None]]
    ] = None
    _ws: typing.Optional[websockets.ClientConnection] = None

    def __init__(
        self,
        apps: list[tuple[inngest.Inngest, list[inngest.Function]]],
        *,
        instance_id: typing.Optional[str] = None,
        max_concurrency: typing.Optional[int] = None,
        handle_shutdown_signals: typing.Optional[list[str]] = None,
        rewrite_gateway_endpoint: typing.Optional[
            typing.Callable[[str], str]
        ] = None,
    ) -> None:
        if handle_shutdown_signals is None:
            handle_shutdown_signals = _default_shutdown_signals

        if len(apps) == 0:
            raise Exception("no apps provided")
        default_client = apps[0][0]
        self._logger = default_client.logger
        self._api_origin = default_client.api_origin
        self._signing_key = None

        self._fallback_signing_key = None
        if default_client._mode == server_lib.ServerKind.CLOUD:
            # We only want to send the signing key in outgoing headers if we're
            # in cloud mode.
            self._signing_key = default_client.signing_key
            self._fallback_signing_key = default_client.signing_key_fallback

        self._comm_handlers: dict[str, comm_lib.CommHandler] = {}
        self._app_configs: dict[str, list[server_lib.FunctionConfig]] = {}
        for a in apps:
            (client, fns) = a

            # Validate that certain app configs are consistent across all apps.
            if client.api_origin != default_client.api_origin:
                raise Exception("inconsistent app config: API base URL")
            if client.env != default_client.env:
                raise Exception("inconsistent app config: env")
            if client._mode != default_client._mode:
                raise Exception("inconsistent app config: mode")
            if client.signing_key != default_client.signing_key:
                raise Exception("inconsistent app config: signing key")

            configs = comm_lib.get_function_configs(
                "wss://connect",
                {fn.id: fn for fn in fns},
            )
            if isinstance(configs, Exception):
                raise configs
            self._app_configs[client.app_id] = configs

            self._comm_handlers[client.app_id] = comm_lib.CommHandler(
                client=client,
                framework=_framework,
                functions=fns,
            )

        if instance_id is None:
            instance_id = socket.gethostname()
        self._instance_id = instance_id

        self._max_concurrency = max_concurrency
        self._handle_shutdown_signals = handle_shutdown_signals
        self._rewrite_gateway_endpoint = rewrite_gateway_endpoint
        self._http_client = net.ThreadAwareAsyncHTTPClient().initialize()
        self._http_client_sync = httpx.Client()

        def on_conn_state_change(
            old_state: ConnectionState,
            new_state: ConnectionState,
        ) -> None:
            self._logger.debug(
                "Connection state changed",
                extra={
                    "old": old_state.value,
                    "new": new_state.value,
                },
            )

        self._state = _State(
            auth_data=None,
            conn_id=None,
            conn_state=_ValueWatcher(
                ConnectionState.CLOSED,
                on_change=on_conn_state_change,
            ),
            exclude_gateways=[],
            gateway_url=_ValueWatcher(None),
            ws=None,
        )

        self._handlers: list[_Handler] = [
            _HeartbeatHandler(self._logger, self._state),
            _InitHandler(
                self._logger,
                self._state,
                self._app_configs,
                default_client.env,
                self._instance_id,
            ),
            _ExecutionHandler(
                self._logger,
                self._state,
                self._comm_handlers,
            ),
        ]

        self._start_requester = _ConnStarter(
            api_origin=self._api_origin,
            http_client=self._http_client,
            http_client_sync=self._http_client_sync,
            logger=self._logger,
            rewrite_gateway_endpoint=self._rewrite_gateway_endpoint,
            signing_key=self._signing_key,
            signing_key_fallback=self._fallback_signing_key,
            state=self._state,
        )

    def get_connection_id(self) -> str:
        if self._state.conn_id is None:
            raise Exception("connection not established")

        return self._state.conn_id

    def get_state(self) -> ConnectionState:
        return self._state.conn_state.value

    async def wait_for_state(self, state: ConnectionState) -> None:
        await self._state.conn_state.wait_for(state)

    async def _handle_msg(
        self,
        ws: websockets.ClientConnection,
    ) -> types.MaybeError[None]:
        try:
            async for raw_msg in ws:
                if self._state.auth_data is None:
                    # Unreachable.
                    self._logger.error("Missing auth data")
                    continue

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
                        "kind": msg.kind,
                        "payload": msg.payload,
                    },
                )

                for h in self._handlers:
                    h.handle_msg(
                        msg,
                        self._state.auth_data,
                        self.get_connection_id(),
                    )

        except websockets.exceptions.ConnectionClosedError as e:
            self._logger.debug(
                "Connection closed abnormally", extra={"error": str(e)}
            )
            self._state.conn_state.value = ConnectionState.RECONNECTING
            self._state.gateway_url.value = None
        except websockets.exceptions.ConnectionClosedOK:
            self._logger.debug("Connection closed normally")
            self._state.conn_state.value = ConnectionState.CLOSED
            self._state.gateway_url.value = None
        except Exception as e:
            self._logger.debug("Connection error", extra={"error": str(e)})
            self._state.conn_state.value = ConnectionState.RECONNECTING
            self._state.gateway_url.value = None
        return None

    async def start(self) -> None:
        self._closed_event = asyncio.Event()
        self._running = True

        err = await self._start_requester.start()
        if isinstance(err, Exception):
            raise err

        while self._closed_event.is_set() is False:
            try:
                await self._state.gateway_url.wait_for_not(None)
                if self._state.gateway_url.value is None:
                    raise _UnreachableError("missing gateway URL")

                self._logger.debug(
                    "Connecting to gateway",
                    extra={"endpoint": self._state.gateway_url.value},
                )

                async with websockets.connect(
                    self._state.gateway_url.value,
                    subprotocols=[_protocol],
                ) as ws:
                    self._state.ws = ws
                    self._message_handler_task = asyncio.create_task(
                        self._handle_msg(ws)
                    )

                    for h in self._handlers:
                        err = h.start()
                        if isinstance(err, Exception):
                            raise err

                    await self._state.gateway_url.wait_for_change()
                    await asyncio.sleep(1)
            except Exception as e:
                self._logger.error(f"Connection error: {e}. Reconnecting...")
                self._state.conn_state.value = ConnectionState.RECONNECTING
                await asyncio.sleep(5)  # Reconnection delay
            finally:
                self._logger.debug("Gateway connection closed")

    async def close(self, *, wait: bool = False) -> None:
        # Tell all the handlers to close.
        for h in self._handlers:
            h.close()

        self._state.conn_state.value = ConnectionState.CLOSED

        if self._closed_event is not None:
            self._closed_event.set()

        if wait:
            await self.closed()

    async def closed(self) -> None:
        if self._closed_event is not None:
            await self._closed_event.wait()

        if self._message_handler_task:
            err = await self._message_handler_task
            if isinstance(err, Exception):
                raise err

        # Wait for all the handlers to close.
        await asyncio.gather(*[h.closed() for h in self._handlers])
