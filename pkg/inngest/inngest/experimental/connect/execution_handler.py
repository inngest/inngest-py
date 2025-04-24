import asyncio
import typing

from inngest._internal import comm_lib, server_lib, types

from . import connect_pb2
from .base_handler import _BaseHandler
from .models import _State


class _ExecutionHandler(_BaseHandler):
    """
    Handles incoming execution requests from the Gateway.
    """

    _leaser_extender_task: typing.Optional[asyncio.Task[None]] = None

    def __init__(
        self,
        logger: types.Logger,
        state: _State,
        comm_handlers: dict[str, comm_lib.CommHandler],
    ) -> None:
        self._comm_handlers = comm_handlers
        self._logger = logger
        self._state = state

        # Keep track of pending tasks to support graceful shutdown and lease
        # extensions.
        self._pending_requests: dict[
            str,
            tuple[connect_pb2.GatewayExecutorRequestData, asyncio.Task[None]],
        ] = {}

    def start(self) -> types.MaybeError[None]:
        err = super().start()
        if err is not None:
            return err

        if self._leaser_extender_task is None:
            self._leaser_extender_task = asyncio.create_task(
                self._leaser_extender()
            )

        return None

    def close(self) -> None:
        super().close()

        if self._leaser_extender_task is not None:
            self._leaser_extender_task.cancel()

    async def closed(self) -> None:
        await super().closed()
        await asyncio.gather(*[t for _, t in self._pending_requests.values()])
        self._pending_requests.clear()

        if self._leaser_extender_task is not None:
            try:
                await self._leaser_extender_task
            except asyncio.CancelledError:
                # This is expected since the task is likely calling
                # `asyncio.sleep` after cancellation.
                pass

    def handle_msg(
        self,
        msg: connect_pb2.ConnectMessage,
        auth_data: connect_pb2.AuthData,
        connection_id: str,
    ) -> None:
        if msg.kind == connect_pb2.GatewayMessageType.GATEWAY_EXECUTOR_REQUEST:
            self._handle_executor_request(msg)
        elif (
            msg.kind
            == connect_pb2.GatewayMessageType.WORKER_REQUEST_EXTEND_LEASE_ACK
        ):
            self._handle_lease_extend_ack(msg)

    def _handle_executor_request(
        self,
        msg: connect_pb2.ConnectMessage,
    ) -> None:
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
            ws = await self._state.ws.wait_for_not_none()
            try:
                await ws.send(
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
                        is_connect=True,
                        query_params={
                            server_lib.QueryParamKey.FUNCTION_ID.value: req_data.function_slug,
                        },
                        raw_request=req_data,
                        request_url="",
                        serve_origin=None,
                        serve_path=None,
                    )
                )
            except Exception as e:
                self._logger.error("Execution failed", extra={"error": str(e)})
                comm_res = comm_lib.CommResponse.from_error(self._logger, e)

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
            await ws.send(
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

        # Store the task.
        task = asyncio.create_task(execute())
        self._pending_requests[req_data.request_id] = (req_data, task)

        # Remove the task when it completes.
        task.add_done_callback(
            lambda _: self._pending_requests.pop(req_data.request_id)
        )

    def _handle_lease_extend_ack(
        self,
        msg: connect_pb2.ConnectMessage,
    ) -> None:
        req_data = connect_pb2.WorkerRequestExtendLeaseAckData()
        req_data.ParseFromString(msg.payload)

        pending_req = self._pending_requests.get(req_data.request_id, None)
        if pending_req is None:
            self._logger.error(
                "Received lease extend ack for unknown request",
                extra={"request_id": req_data.request_id},
            )
            return

        # Each lease extension ack includes a new lease ID. If we don't use the
        # new lease ID the next time we extend, we'll have a bad time.
        pending_req[0].lease_id = req_data.new_lease_id

    async def _leaser_extender(self) -> None:
        ws = await self._state.ws.wait_for_not_none()
        extend_lease_interval = (
            await self._state.extend_lease_interval.wait_for_not_none()
        )

        while self.closed_event.is_set() is False:
            await asyncio.sleep(extend_lease_interval)

            if len(self._pending_requests) == 0:
                continue

            self._logger.debug(
                "Extending leases", extra={"count": len(self._pending_requests)}
            )

            for req_data, _ in self._pending_requests.values():
                try:
                    await ws.send(
                        connect_pb2.ConnectMessage(
                            kind=connect_pb2.GatewayMessageType.WORKER_REQUEST_EXTEND_LEASE,
                            payload=connect_pb2.WorkerRequestExtendLeaseData(
                                account_id=req_data.account_id,
                                env_id=req_data.env_id,
                                function_slug=req_data.function_slug,
                                lease_id=req_data.lease_id,
                                request_id=req_data.request_id,
                                run_id=req_data.run_id,
                                step_id=req_data.step_id,
                                system_trace_ctx=req_data.system_trace_ctx,
                                user_trace_ctx=req_data.user_trace_ctx,
                            ).SerializeToString(),
                        ).SerializeToString()
                    )
                except Exception as e:
                    self._logger.error(
                        "Failed to extend lease", extra={"error": str(e)}
                    )
