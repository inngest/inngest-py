from __future__ import annotations

import asyncio
import signal
import socket
import typing

import httpx
import websockets

import inngest
from inngest._internal import comm_lib, net, server_lib, types

from . import connect_pb2
from .base_handler import _BaseHandler
from .conn_init_starter import _ConnInitHandler
from .consts import (
    _default_shutdown_signals,
    _framework,
    _protocol,
)
from .drain_handler import _DrainHandler
from .errors import _UnreachableError
from .execution_handler import _ExecutionHandler
from .heartbeat_handler import _HeartbeatHandler
from .init_handshake_handler import _InitHandshakeHandler
from .models import ConnectionState, _State
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
    _consumers_closed_task: typing.Optional[asyncio.Task[None]] = None
    _event_loop_keep_alive_task: typing.Optional[asyncio.Task[None]] = None

    _message_handler_task: typing.Optional[
        asyncio.Task[types.MaybeError[None]]
    ] = None

    def __init__(
        self,
        apps: list[tuple[inngest.Inngest, list[inngest.Function]]],
        *,
        instance_id: typing.Optional[str] = None,
        max_concurrency: typing.Optional[int] = None,
        rewrite_gateway_endpoint: typing.Optional[
            typing.Callable[[str], str]
        ] = None,
        shutdown_signals: typing.Optional[list[signal.Signals]] = None,
    ) -> None:
        # Used to ensure that no messages are being handled when we fully close.
        self._handling_message_count = _ValueWatcher(0)

        if shutdown_signals is None:
            shutdown_signals = _default_shutdown_signals
        for sig in shutdown_signals:
            signal.signal(sig, lambda _, __: self._close())

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
                streaming=False,  # Probably doesn't make sense for Connect.
            )

        if instance_id is None:
            instance_id = socket.gethostname()
        self._instance_id = instance_id

        self._max_concurrency = max_concurrency
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
            conn_id=None,
            conn_init=_ValueWatcher(None),
            conn_state=_ValueWatcher(
                ConnectionState.CONNECTING,
                on_change=on_conn_state_change,
            ),
            draining=_ValueWatcher(False),
            exclude_gateways=[],
            extend_lease_interval=_ValueWatcher(None),
            fatal_error=_ValueWatcher(None),
            ws=_ValueWatcher(None),
        )

        self._handlers: list[_BaseHandler] = [
            _ConnInitHandler(
                api_origin=self._api_origin,
                http_client=self._http_client,
                http_client_sync=self._http_client_sync,
                logger=self._logger,
                rewrite_gateway_endpoint=self._rewrite_gateway_endpoint,
                signing_key=self._signing_key,
                signing_key_fallback=self._fallback_signing_key,
                state=self._state,
            ),
            _HeartbeatHandler(self._logger, self._state),
            _InitHandshakeHandler(
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
            _DrainHandler(self._logger, self._state),
        ]

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
                if self._state.conn_init.value is None:
                    return _UnreachableError("Missing conn init")

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

                self._handling_message_count.value += 1
                try:
                    for h in self._handlers:
                        h.handle_msg(
                            msg,
                            self._state.conn_init.value[0],
                            self.get_connection_id(),
                        )
                finally:
                    self._handling_message_count.value -= 1

        except websockets.exceptions.ConnectionClosedError as e:
            self._logger.debug(
                "Connection closed abnormally", extra={"error": str(e)}
            )
            self._state.conn_state.value = ConnectionState.RECONNECTING
            self._state.conn_init.value = None
        except websockets.exceptions.ConnectionClosedOK:
            self._logger.debug("Connection closed normally")
            await self.close()
        except Exception as e:
            self._logger.debug("Connection error", extra={"error": str(e)})
            self._state.conn_state.value = ConnectionState.RECONNECTING
            self._state.conn_init.value = None
        return None

    async def start(self) -> None:
        self._event_loop_keep_alive_task = _event_loop_keep_alive()

        for h in self._handlers:
            err = h.start()
            if isinstance(err, Exception):
                raise err

        self._consumers_closed_task = asyncio.create_task(
            self._wait_for_consumers_closed(),
        )

        while self._state.conn_state.value not in [
            ConnectionState.CLOSED,
            ConnectionState.CLOSING,
        ]:
            gateway_endpoint = await _wait_for_gateway_endpoint(self._state)
            if isinstance(gateway_endpoint, Exception):
                # Fatal error.
                raise gateway_endpoint
            endpoint, closing = gateway_endpoint
            if closing:
                return

            try:
                self._logger.debug(
                    "Gateway connecting",
                    extra={"endpoint": endpoint},
                )

                async with websockets.connect(
                    endpoint,
                    subprotocols=[_protocol],
                ) as ws:
                    self._logger.debug("Gateway connected")
                    self._state.ws.value = ws
                    self._message_handler_task = asyncio.create_task(
                        self._handle_msg(ws)
                    )

                    await self._state.conn_init.wait_for_change()
                    await asyncio.sleep(1)
            except Exception as e:
                self._logger.error(
                    f"Gateway connection error: {e}. Reconnecting..."
                )
                self._state.conn_state.value = ConnectionState.RECONNECTING
                await asyncio.sleep(5)  # Reconnection delay
            except asyncio.CancelledError:
                # TODO: Figure out why we reach here sometimes.
                pass
            finally:
                self._logger.debug("Gateway connection closed")

    async def close(self, *, wait: bool = False) -> None:
        self._close()

        if wait:
            await self.closed()

    def _close(self) -> None:
        """
        Must be sync since it's called in signal handlers.
        """

        if self._state.conn_state.value == ConnectionState.CLOSED:
            # Already closed.
            return

        self._state.conn_state.value = ConnectionState.CLOSING

        # Tell all the handlers to close.
        for h in self._handlers:
            h.close()

    async def closed(self) -> None:
        if self._state.conn_state.value == ConnectionState.CLOSED:
            # Already closed.
            return

        await self._wait_for_consumers_closed()
        self._state.conn_state.value = ConnectionState.CLOSED

        if self._event_loop_keep_alive_task is not None:
            self._event_loop_keep_alive_task.cancel()

    async def _wait_for_consumers_closed(self) -> None:
        """
        Wait for all consumers to close. The WebSocket connection should not
        close until then.
        """

        await asyncio.gather(*[h.closed() for h in self._handlers])
        await self._handling_message_count.wait_for(0)
        self._state.conn_init.value = None


def _event_loop_keep_alive() -> asyncio.Task[None]:
    """
    Create a task whose sole purpose is to keep the event loop alive. Without
    this, the event loop can go into an idle mode. This isn't a huge deal, but
    it can make graceful shutdown take ~5 seconds longer.
    """

    async def _keep_alive() -> None:
        while True:  # noqa: ASYNC110
            await asyncio.sleep(1)

    return asyncio.create_task(_keep_alive())


async def _wait_for_gateway_endpoint(
    state: _State,
) -> types.MaybeError[tuple[str, bool]]:
    """
    Wait for the Gateway endpoint to be set or for the connection to be closing.
    Returns the Gateway endpoint and a boolean indicating if the connection is
    closing.
    """

    done_tasks, _ = await asyncio.wait(
        (
            asyncio.create_task(state.conn_init.wait_for_not_none()),
            asyncio.create_task(
                state.conn_state.wait_for(ConnectionState.CLOSING)
            ),
            asyncio.create_task(state.fatal_error.wait_for_not_none()),
        ),
        return_when=asyncio.FIRST_COMPLETED,
    )

    for t in done_tasks:
        # Need to cast because Mypy doesn't understand the type (it thinks it's
        # `object`).
        r = typing.cast(
            typing.Union[
                ConnectionState,
                tuple[connect_pb2.AuthData, str],
                Exception,
            ],
            t.result(),
        )

        if r is ConnectionState.CLOSING:
            # We need to shutdown.
            return ("", True)
        if isinstance(r, Exception):
            return r
        if isinstance(r, ConnectionState):
            return _UnreachableError(
                "We already checked the only possible ConnectionState"
            )

        return r[1], False

    return _UnreachableError()
