import asyncio
import dataclasses
import platform
import typing

import psutil
import pydantic_core

from inngest._internal import const, server_lib, types

from . import connect_pb2
from .base_handler import _BaseHandler
from .models import ConnectionState, _State


class _InitHandshakeHandler(_BaseHandler):
    _closed_event: typing.Optional[asyncio.Event] = None
    _drain_task: typing.Optional[asyncio.Task[None]] = None
    _send_data_task: typing.Optional[asyncio.Task[None]] = None
    _reconnect_task: typing.Optional[asyncio.Task[None]] = None

    def __init__(
        self,
        logger: types.Logger,
        state: _State,
        app_configs: dict[str, list[server_lib.FunctionConfig]],
        env: typing.Optional[str],
        instance_id: str,
    ) -> None:
        self._app_configs = app_configs
        self._env = env
        self._instance_id = instance_id
        self._logger = logger
        self._kind_state = _KindState()
        self._state = state

    def start(self) -> types.MaybeError[None]:
        err = super().start()
        if err is not None:
            return err

        if self._drain_task is None:
            self._drain_task = asyncio.create_task(
                self._drain_watcher(self.closed_event)
            )

        if self._reconnect_task is None:
            self._reconnect_task = asyncio.create_task(
                self._reconnect_watcher(self.closed_event)
            )
        return None

    def close(self) -> None:
        super().close()

        if self._send_data_task is not None:
            self._send_data_task.cancel()

    async def closed(self) -> None:
        await super().closed()

        if self._send_data_task is not None:
            try:
                await self._send_data_task
            except asyncio.CancelledError:
                # Expected.
                pass

    async def _drain_watcher(self, closed_event: asyncio.Event) -> None:
        while closed_event.is_set() is False:
            await self._state.draining.wait_for(True, immediate=False)

            # Reset the kind state so that we redo initialization.
            self._kind_state = _KindState()

    async def _reconnect_watcher(self, closed_event: asyncio.Event) -> None:
        while closed_event.is_set() is False:
            await self._state.conn_state.wait_for(
                ConnectionState.RECONNECTING,
                immediate=False,
            )

            # Reset the kind state so that we redo initialization.
            self._kind_state = _KindState()

    def handle_msg(
        self,
        msg: connect_pb2.ConnectMessage,
        auth_data: connect_pb2.AuthData,
        connection_id: str,
    ) -> None:
        if self._kind_state.GATEWAY_HELLO is False:
            if msg.kind != connect_pb2.GatewayMessageType.GATEWAY_HELLO:
                self._logger.error("Expected GATEWAY_HELLO")
                return
            self._kind_state.GATEWAY_HELLO = True

        if self._kind_state.SYNCED is False:
            self._logger.debug("Syncing")

            if (
                self._send_data_task is not None
                and not self._send_data_task.done()
            ):
                self._logger.debug("Replacing existing sync task")
                self._send_data_task.cancel()

            self._send_data_task = asyncio.create_task(
                self._send_response(
                    auth_data,
                    connection_id,
                )
            )
            return None

        if self._kind_state.GATEWAY_CONNECTION_READY is False:
            if (
                msg.kind
                != connect_pb2.GatewayMessageType.GATEWAY_CONNECTION_READY
            ):
                self._logger.error("Expected GATEWAY_CONNECTION_READY")
            self._kind_state.GATEWAY_CONNECTION_READY = True
            self._state.conn_state.value = ConnectionState.ACTIVE

        return None

    async def _send_response(
        self,
        auth_data: connect_pb2.AuthData,
        connection_id: str,
    ) -> None:
        ws = await self._state.ws.wait_for_not_none()

        sync_message = _create_sync_message(
            apps_configs=self._app_configs,
            auth_data=auth_data,
            connection_id=connection_id,
            env=self._env,
            instance_id=self._instance_id,
        )
        if isinstance(sync_message, Exception):
            self._logger.error(
                "Failed to create sync message",
                extra={"error": str(sync_message)},
            )
            return

        await ws.send(sync_message.SerializeToString())
        self._kind_state.SYNCED = True
        return None


@dataclasses.dataclass
class _KindState:
    GATEWAY_HELLO: bool = False
    GATEWAY_CONNECTION_READY: bool = False
    SYNCED: bool = False


def _create_sync_message(
    *,
    apps_configs: dict[str, list[server_lib.FunctionConfig]],
    auth_data: connect_pb2.AuthData,
    connection_id: str,
    env: typing.Optional[str],
    instance_id: str,
) -> types.MaybeError[connect_pb2.ConnectMessage]:
    apps: list[connect_pb2.AppConfiguration] = []
    for app_id, functions in apps_configs.items():
        try:
            functions_bytes = pydantic_core.to_json(functions)
        except Exception as err:
            return err

        apps.append(
            connect_pb2.AppConfiguration(
                app_name=app_id,
                functions=functions_bytes,
            )
        )

    capabilities = server_lib.Capabilities().model_dump_json().encode("utf-8")

    payload = connect_pb2.WorkerConnectRequestData(
        apps=apps,
        auth_data=auth_data,
        capabilities=capabilities,
        connection_id=connection_id,
        environment=env,
        framework=server_lib.Framework.CONNECT.value,
        instance_id=instance_id,
        sdk_language=const.LANGUAGE,
        sdk_version=const.VERSION,
        system_attributes=connect_pb2.SystemAttributes(
            cpu_cores=psutil.cpu_count(),
            mem_bytes=psutil.virtual_memory().total,
            os=platform.system().lower(),
        ),
        worker_manual_readiness_ack=False,
    )

    return connect_pb2.ConnectMessage(
        kind=connect_pb2.GatewayMessageType.WORKER_CONNECT,
        payload=payload.SerializeToString(),
    )
