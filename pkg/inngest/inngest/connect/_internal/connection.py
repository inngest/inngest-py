"""
Main orchestrator for the Connect WebSocket connection.

This module provides the primary entry point for establishing and managing
persistent WebSocket connections between the SDK and the Inngest server.

Thread ownership:
    This module contains only main-thread concerns: public API, signal
    handling, thread creation, and bridging into the internal thread.
    Internal-thread logic (WebSocket lifecycle, message handling, shutdown
    coordination) lives in `isolated_worker.py`.
"""

from __future__ import annotations

import asyncio
import signal
import socket
import threading
import typing

import httpx

import inngest
from inngest._internal import comm_lib, const, net, server_lib

from .configs_lib import get_max_worker_concurrency
from .conn_init_starter import ConnInitHandler
from .consts import (
    DEFAULT_SHUTDOWN_SIGNALS,
    FRAMEWORK,
    HEARTBEAT_INTERVAL_SEC,
)
from .drain_handler import DrainHandler
from .errors import UnreachableError
from .execution_handler import ExecutionHandler
from .heartbeat_handler import HeartbeatHandler
from .init_handshake_handler import InitHandshakeHandler
from .isolated_worker import IsolatedWorker
from .models import AppConfig, ConnectionState, State
from .value_watcher import ValueWatcher


class WorkerConnection(typing.Protocol):
    """
    Connection between the SDK and Inngest server.
    """

    async def close(self, *, wait: bool = False) -> None:
        """
        Close the connection.

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
        Start the connection. Blocks until the connection is closed.
        """
        ...

    async def wait_for_state(self, state: ConnectionState) -> None:
        """
        Wait for the connection to reach a specific state.
        """
        ...


class WorkerConnectionImpl(WorkerConnection):
    _loop: asyncio.AbstractEventLoop | None = None
    _thread: threading.Thread | None = None

    def __init__(
        self,
        apps: list[tuple[inngest.Inngest, list[inngest.Function[typing.Any]]]],
        *,
        instance_id: str | None = None,
        rewrite_gateway_endpoint: typing.Callable[[str], str] | None = None,
        shutdown_signals: list[signal.Signals] | None = None,
        max_worker_concurrency: int | None = None,
        _test_only_heartbeat_interval_sec: int | None = None,
        _test_only_extend_lease_interval: int | None = None,
    ) -> None:
        if len(apps) == 0:
            raise Exception("no apps provided")
        default_client = apps[0][0]
        self._logger = default_client.logger
        self._api_origin = default_client.api_origin
        self._signing_key = None

        if shutdown_signals is None:
            shutdown_signals = DEFAULT_SHUTDOWN_SIGNALS

        # Only set up signal handlers if we're in the main thread. Otherwise,
        # we'll get a "signal only works in main thread" error when outside the
        # main thread
        if threading.current_thread() is threading.main_thread():
            for sig in shutdown_signals:
                signal.signal(sig, lambda _, __: self._close())
        else:
            self._logger.debug(
                "Skipping signal handlers because this isn't the main thread"
            )

        self._fallback_signing_key = None
        if default_client._mode == server_lib.ServerKind.CLOUD:
            # We only want to send the signing key in outgoing headers if we're
            # in cloud mode.
            self._signing_key = default_client.signing_key
            self._fallback_signing_key = default_client.signing_key_fallback

        self._comm_handlers: dict[str, comm_lib.CommHandler] = {}
        self._app_configs: dict[str, AppConfig] = {}
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
            self._app_configs[client.app_id] = AppConfig(
                functions=configs,
                version=client.app_version,
            )

            self._comm_handlers[client.app_id] = comm_lib.CommHandler(
                client=client,
                framework=FRAMEWORK,
                functions=fns,
                streaming=const.Streaming.DISABLE,  # Probably doesn't make sense for Connect.
            )

        if instance_id is None:
            instance_id = socket.gethostname()
        self._instance_id = instance_id
        # Maximum number of worker concurrency to use. Defaults to None.
        if max_worker_concurrency is None:
            max_worker_concurrency = get_max_worker_concurrency()
        self._max_worker_concurrency = max_worker_concurrency

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

        self._state = State(
            conn_id=ValueWatcher(None),
            conn_init=ValueWatcher(None),
            conn_state=ValueWatcher(
                ConnectionState.CONNECTING,
                on_change=on_conn_state_change,
            ),
            exclude_gateways=ValueWatcher([]),
            extend_lease_interval=ValueWatcher(None),
            fatal_error=ValueWatcher(None),
            init_handshake_complete=ValueWatcher(False),
            pending_request_count=ValueWatcher(0),
            ws=ValueWatcher(None),
        )

        self._execution_handler = ExecutionHandler(
            api_origin=self._api_origin,
            comm_handlers=self._comm_handlers,
            http_client=self._http_client,
            http_client_sync=self._http_client_sync,
            logger=self._logger,
            state=self._state,
            signing_key=self._signing_key,
            signing_key_fallback=self._fallback_signing_key,
        )

        self._handlers = [
            ConnInitHandler(
                api_origin=self._api_origin,
                env=default_client.env,
                http_client=self._http_client,
                http_client_sync=self._http_client_sync,
                logger=self._logger,
                rewrite_gateway_endpoint=self._rewrite_gateway_endpoint,
                signing_key=self._signing_key,
                signing_key_fallback=self._fallback_signing_key,
                state=self._state,
            ),
            HeartbeatHandler(
                self._logger,
                self._state,
                _test_only_heartbeat_interval_sec or HEARTBEAT_INTERVAL_SEC,
            ),
            InitHandshakeHandler(
                self._logger,
                self._state,
                self._app_configs,
                default_client.env,
                self._instance_id,
                max_worker_concurrency=self._max_worker_concurrency,
                _test_only_extend_lease_interval=_test_only_extend_lease_interval,
            ),
            self._execution_handler,
            DrainHandler(self._logger, self._state),
        ]

        self._isolated_worker = IsolatedWorker(
            handlers=self._handlers,
            state=self._state,
            logger=self._logger,
        )

    def get_connection_id(self) -> str:
        conn_id = self._state.conn_id.value
        if conn_id is None:
            raise Exception("connection not established")

        return conn_id

    def get_state(self) -> ConnectionState:
        return self._state.conn_state.value

    async def wait_for_state(self, state: ConnectionState) -> None:
        await self._state.conn_state.wait_for(state)

    async def start(self) -> None:
        # User functions execute on the caller's loop (main thread).
        self._execution_handler._main_loop = asyncio.get_running_loop()

        # Created here so `_close` can call `call_soon_threadsafe` on it
        # before the thread starts. The loop isn't *run* until `run_connect`.
        self._loop = asyncio.new_event_loop()
        thread_exc: Exception | None = None

        def run_connect() -> None:
            nonlocal thread_exc
            if self._loop is None:
                raise UnreachableError("loop is None")
            try:
                self._loop.run_until_complete(self._isolated_worker.run())
            except Exception as e:
                thread_exc = e
                # Ensure CLOSED is reached even if run() raised
                # before its try/finally block.
                self._state.conn_state.set_if(
                    ConnectionState.CLOSED,
                    lambda v: v != ConnectionState.CLOSED,
                )
            finally:
                _shutdown_loop(self._loop)

        self._thread = threading.Thread(target=run_connect, daemon=True)
        self._thread.start()

        # Block until the connection reaches CLOSED state.
        await self._state.conn_state.wait_for(ConnectionState.CLOSED)
        await asyncio.to_thread(self._thread.join)

        await self._http_client.aclose()
        self._http_client_sync.close()

        if thread_exc is not None:
            raise thread_exc

    async def close(self, *, wait: bool = False) -> None:
        self._close()

        if wait:
            await self.closed()

    def _close(self) -> None:
        """
        Must be sync since it's called in signal handlers.
        """

        did_set = self._state.conn_state.set_if(
            ConnectionState.CLOSING,
            lambda v: v
            not in (ConnectionState.CLOSING, ConnectionState.CLOSED),
        )
        if not did_set:
            # Already closed or closing.
            return

        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(
                    self._isolated_worker.schedule_close
                )
            except RuntimeError:
                # Loop already closed (worker thread exited on its own).
                pass

    async def closed(self) -> None:
        await self._state.conn_state.wait_for(ConnectionState.CLOSED)

        if self._thread is not None:
            await asyncio.to_thread(self._thread.join)


def _shutdown_loop(loop: asyncio.AbstractEventLoop) -> None:
    """
    Cancel all remaining tasks on the loop and close it. Called from the worker
    thread after `run_until_complete` returns.
    """

    try:
        pending = asyncio.all_tasks(loop)
        for t in pending:
            t.cancel()
    finally:
        loop.close()
