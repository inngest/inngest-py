import asyncio
import dataclasses
import platform
import re

import psutil
import pydantic_core

from inngest._internal import const, errors, server_lib, types

from . import connect_pb2
from .base_handler import _BaseHandler
from .models import ConnectionState, _State


class _InitHandshakeHandler(_BaseHandler):
    _closed_event: asyncio.Event | None = None
    _send_data_task: asyncio.Task[None] | None = None
    _reconnect_task: asyncio.Task[None] | None = None

    def __init__(
        self,
        logger: types.Logger,
        state: _State,
        app_configs: dict[str, list[server_lib.FunctionConfig]],
        env: str | None,
        instance_id: str,
        max_worker_concurrency: int | None = None,
    ) -> None:
        self._app_configs = app_configs
        self._env = env
        self._instance_id = instance_id
        self._logger = logger
        self._kind_state = _KindState()
        self._state = state
        self._max_worker_concurrency = max_worker_concurrency

    def start(self) -> types.MaybeError[None]:
        err = super().start()
        if err is not None:
            return err

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

    async def _reconnect_watcher(self, closed_event: asyncio.Event) -> None:
        while closed_event.is_set() is False:
            await self._state.conn_init.wait_for(None, immediate=False)

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
            return

        if self._kind_state.GATEWAY_CONNECTION_READY is False:
            if (
                msg.kind
                != connect_pb2.GatewayMessageType.GATEWAY_CONNECTION_READY
            ):
                self._logger.error("Expected GATEWAY_CONNECTION_READY")
                return

            req_data = connect_pb2.GatewayConnectionReadyData()
            req_data.ParseFromString(msg.payload)

            extend_lease_interval = _duration_str_to_sec(
                req_data.extend_lease_interval
            )
            if isinstance(extend_lease_interval, Exception):
                self._logger.error(
                    "Failed to parse extend_lease_interval",
                )
            else:
                self._state.extend_lease_interval.value = extend_lease_interval
                self._logger.debug(
                    "Set extend lease interval",
                    extra={"value": extend_lease_interval},
                )

            self._kind_state.GATEWAY_CONNECTION_READY = True
            self._state.conn_state.value = ConnectionState.ACTIVE

        return

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
            max_worker_concurrency=self._max_worker_concurrency,
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
    env: str | None,
    instance_id: str,
    max_worker_concurrency: int | None = None,
) -> types.MaybeError[connect_pb2.ConnectMessage]:
    apps: list[connect_pb2.AppConfiguration] = []
    for app_id, functions in apps_configs.items():
        try:
            functions_bytes = pydantic_core.to_json(
                functions, exclude_none=True
            )
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
        max_worker_concurrency=max_worker_concurrency,
    )

    return connect_pb2.ConnectMessage(
        kind=connect_pb2.GatewayMessageType.WORKER_CONNECT,
        payload=payload.SerializeToString(),
    )


def _duration_str_to_sec(duration_str: str) -> types.MaybeError[int]:
    """
    Convert a duration string (e.g. "10s") to a number of seconds. Does not
    support any other units (e.g. "1m" will error).
    """

    regex = r"^(\d+)s$"
    match = re.match(regex, duration_str)
    if match is None:
        return errors.UnreachableError(
            f"Invalid duration string: {duration_str}"
        )

    try:
        return int(match.group(1))
    except Exception:
        return errors.UnreachableError(
            f"Invalid duration string: {duration_str}"
        )
