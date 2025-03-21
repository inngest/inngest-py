import asyncio
import dataclasses
import typing

import pydantic_core
import websockets

from inngest._internal import const, server_lib, types

from . import connect_pb2
from .models import ConnectionState, _State


class _InitHandler:
    _send_data_task: typing.Optional[asyncio.Task[None]] = None
    _state_watcher_task: typing.Optional[asyncio.Task[None]] = None
    _ws: typing.Optional[websockets.ClientConnection] = None

    def __init__(
        self,
        logger: types.Logger,
        state: _State,
        app_configs: dict[str, list[server_lib.FunctionConfig]],
        env: typing.Optional[str],
    ) -> None:
        self._app_configs = app_configs
        self._env = env
        self._logger = logger
        self._kind_state = _KindState()
        self._state = state

    def start(
        self,
        ws: websockets.ClientConnection,
    ) -> types.MaybeError[None]:
        self._ws = ws
        if self._send_data_task is not None:
            # Unreachable.
            return Exception("init handler already started")
        self._state_watcher_task = asyncio.create_task(self._state_watcher())
        return None

    def close(self) -> None:
        if self._send_data_task is None:
            return
        self._send_data_task.cancel()

    async def closed(self) -> None:
        if self._send_data_task is not None:
            await self._send_data_task

    async def _state_watcher(self) -> None:
        async for state in self._state.conn_state.watch():
            if state == ConnectionState.RECONNECTING:
                # Reset the kind state when we reconnect.
                self._kind_state = _KindState()

    def handle_msg(
        self,
        msg: connect_pb2.ConnectMessage,
        auth_data: connect_pb2.AuthData,
        connection_id: str,
    ) -> None:
        if self._ws is None:
            # Unreachable.
            raise Exception("missing websocket")

        if self._kind_state.GATEWAY_HELLO is False:
            if msg.kind != connect_pb2.GatewayMessageType.GATEWAY_HELLO:
                self._logger.error("Expected GATEWAY_HELLO")
                return
            self._kind_state.GATEWAY_HELLO = True

        if self._kind_state.SYNCED is False:
            self._logger.debug("Syncing")

            sync_message = _create_sync_message(
                apps_configs=self._app_configs,
                auth_data=auth_data,
                connection_id=connection_id,
                env=self._env,
            )
            if isinstance(sync_message, Exception):
                self._logger.error(
                    "Failed to create sync message",
                    extra={"error": str(sync_message)},
                )

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
        sync_message = _create_sync_message(
            apps_configs=self._app_configs,
            auth_data=auth_data,
            connection_id=connection_id,
            env=self._env,
        )
        if isinstance(sync_message, Exception):
            self._logger.error(
                "Failed to create sync message",
                extra={"error": str(sync_message)},
            )
            return

        if self._ws is None or self._ws.close_reason is not None:
            return None
        await self._ws.send(sync_message.SerializeToString())
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
        connection_id=connection_id,
        environment=env,
        auth_data=auth_data,
        sdk_language=const.LANGUAGE,
        sdk_version=const.VERSION,
        framework=server_lib.Framework.CONNECT.value,
        # TODO
        worker_manual_readiness_ack=False,
        # TODO
        system_attributes=connect_pb2.SystemAttributes(
            cpu_cores=1,
            mem_bytes=1024 * 1024 * 1024,
            os="linux",
        ),
        # TODO
        apps=apps,
        capabilities=capabilities,
        # TODO
        instance_id="foo",
    )

    return connect_pb2.ConnectMessage(
        kind=connect_pb2.GatewayMessageType.WORKER_CONNECT,
        payload=payload.SerializeToString(),
    )
