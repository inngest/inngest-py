import asyncio
import typing

import websockets

from inngest._internal import comm_lib, server_lib, types

from . import connect_pb2


class _ExecutionHandler:
    """
    Handles incoming execution requests from the Gateway.
    """

    _ws: typing.Optional[websockets.ClientConnection] = None

    def __init__(
        self,
        logger: types.Logger,
        comm_handlers: dict[str, comm_lib.CommHandler],
    ) -> None:
        self._comm_handlers = comm_handlers
        self._logger = logger

        # Keep track of pending tasks to allow for graceful shutdown.
        self._pending_tasks: set[asyncio.Task[None]] = set()

    def start(
        self,
        ws: websockets.ClientConnection,
    ) -> types.MaybeError[None]:
        self._ws = ws
        return None

    def close(self) -> None:
        pass

    async def closed(self) -> None:
        await asyncio.gather(*self._pending_tasks)
        self._pending_tasks.clear()

    def handle_msg(
        self,
        msg: connect_pb2.ConnectMessage,
        auth_data: connect_pb2.AuthData,
        connection_id: str,
    ) -> None:
        if msg.kind != connect_pb2.GatewayMessageType.GATEWAY_EXECUTOR_REQUEST:
            return

        self._logger.debug("Received executor request")

        req_data = connect_pb2.GatewayExecutorRequestData()
        req_data.ParseFromString(msg.payload)

        comm_handler = self._comm_handlers.get(req_data.app_name)
        if comm_handler is None:
            self._logger.error(
                "Unknown app",
                extra={"app_id": req_data.app_name},
            )
            return

        async def execute() -> None:
            if self._ws is None:
                # Unreachable.
                self._logger.error("No connection")
                return

            try:
                await self._ws.send(
                    connect_pb2.ConnectMessage(
                        kind=connect_pb2.GatewayMessageType.WORKER_REQUEST_ACK,
                        payload=connect_pb2.WorkerRequestAckData(
                            account_id=req_data.account_id,
                            app_id=req_data.app_id,
                            env_id=req_data.env_id,
                            function_slug=req_data.function_slug,
                            request_id=req_data.request_id,
                            step_id=req_data.step_id,
                            system_trace_ctx=req_data.system_trace_ctx,
                            user_trace_ctx=req_data.user_trace_ctx,
                        ).SerializeToString(),
                    ).SerializeToString()
                )

                comm_res = await comm_handler.post(
                    comm_lib.CommRequest(
                        body=req_data.request_payload,
                        headers={},
                        query_params={
                            server_lib.QueryParamKey.FUNCTION_ID.value: req_data.function_slug,
                        },
                        raw_request=req_data,
                        request_url="",
                        serve_origin=None,
                        serve_path=None,
                    )
                )

                body = comm_res.body_bytes()
                if isinstance(body, Exception):
                    raise body

                status: connect_pb2.SDKResponseStatus
                if comm_res.status_code == 200:
                    # Function-level success.
                    status = connect_pb2.SDKResponseStatus.DONE
                elif comm_res.status_code == 206:
                    # Step-level success.
                    status = connect_pb2.SDKResponseStatus.NOT_COMPLETED
                elif comm_res.status_code == 500:
                    # Error.
                    status = connect_pb2.SDKResponseStatus.ERROR
                else:
                    # Unreachable.
                    status = connect_pb2.SDKResponseStatus.ERROR
                    self._logger.error(
                        "Unexpected status code",
                        extra={"status_code": comm_res.status_code},
                    )

                self._logger.debug("Sending execution reply")
                await self._ws.send(
                    connect_pb2.ConnectMessage(
                        kind=connect_pb2.GatewayMessageType.WORKER_REPLY,
                        payload=connect_pb2.SDKResponse(
                            account_id=req_data.account_id,
                            app_id=req_data.app_id,
                            body=body,
                            env_id=req_data.env_id,
                            no_retry=comm_res.no_retry,
                            request_id=req_data.request_id,
                            request_version=comm_res.request_version,
                            retry_after=comm_res.retry_after,
                            sdk_version=comm_res.sdk_version,
                            status=status,
                            system_trace_ctx=req_data.system_trace_ctx,
                            user_trace_ctx=req_data.user_trace_ctx,
                        ).SerializeToString(),
                    ).SerializeToString()
                )

            except Exception as e:
                self._logger.error("Execution failed", extra={"error": str(e)})

        # Store the task.
        task = asyncio.create_task(execute())
        self._pending_tasks.add(task)

        # Remove the task when it completes.
        task.add_done_callback(self._pending_tasks.discard)
