import asyncio
import typing
import urllib.parse

import httpx

from inngest._internal import comm_lib, net, server_lib, types

from . import connect_pb2, ws_utils
from .base_handler import BaseHandler
from .buffer import SizeConstrainedBuffer
from .consts import DEFAULT_MAX_BUFFER_SIZE_BYTES
from .models import State
from .value_watcher import ValueWatcher

PendingRequest: typing.TypeAlias = tuple[
    connect_pb2.GatewayExecutorRequestData,
    asyncio.Task[None],
]


class _PendingRequestManager:
    def __init__(self, pending_request_count: ValueWatcher[int]) -> None:
        self._pending_request_count = pending_request_count
        self._pending_requests: dict[str, PendingRequest] = {}

    def add(
        self,
        request_id: str,
        request_data: connect_pb2.GatewayExecutorRequestData,
        task: asyncio.Task[None],
    ) -> None:
        self._pending_requests[request_id] = (request_data, task)
        self._pending_request_count.value += 1

    def clear(self) -> None:
        self._pending_requests.clear()
        self._pending_request_count.value = 0

    def count(self) -> int:
        return len(self._pending_requests)

    def get(self, request_id: str) -> PendingRequest | None:
        return self._pending_requests.get(request_id, None)

    def get_all(
        self,
    ) -> list[PendingRequest]:
        return list(self._pending_requests.values())

    def pop(self, request_id: str) -> PendingRequest:
        req = self._pending_requests.pop(request_id)
        self._pending_request_count.value -= 1
        return req


class ExecutionHandler(BaseHandler):
    """
    Handles GATEWAY_EXECUTOR_REQUEST messages containing function invocations.

    Manages the full execution lifecycle:
        1. Receive execution request
        2. Send WORKER_REQUEST_ACK to confirm receipt
        3. Execute the function via the CommHandler
        4. Send WORKER_REPLY with execution result
        5. Wait for WORKER_REPLY_ACK to confirm receipt

    Additional responsibilities:
        - Lease extension: Long-running functions need periodic lease renewals
          to prevent the server from timing out and retrying the request.
        - Unacked message flushing: If WORKER_REPLY_ACK isn't received in time,
          the reply is flushed via HTTP as a fallback.
        - Pending request tracking: Graceful shutdown waits for all pending
          requests to complete before closing.
    """

    _leaser_extender_task: asyncio.Task[None] | None = None
    _unacked_msg_flush_poller_task: asyncio.Task[None] | None = None

    def __init__(
        self,
        api_origin: str,
        comm_handlers: dict[str, comm_lib.CommHandler],
        http_client: net.ThreadAwareAsyncHTTPClient,
        http_client_sync: httpx.Client,
        logger: types.Logger,
        signing_key: str | None,
        signing_key_fallback: str | None,
        state: State,
    ) -> None:
        self._api_origin = api_origin
        self._buffer = SizeConstrainedBuffer(DEFAULT_MAX_BUFFER_SIZE_BYTES)
        self._comm_handlers = comm_handlers
        self._http_client = http_client
        self._http_client_sync = http_client_sync
        self._logger = logger
        self._signing_key = signing_key
        self._signing_key_fallback = signing_key_fallback
        self._state = state

        # Keep track of pending tasks to support graceful shutdown and lease
        # extensions.
        self._pending_requests = _PendingRequestManager(
            state.pending_request_count
        )

    def start(self) -> types.MaybeError[None]:
        err = super().start()
        if err is not None:
            return err

        if self._leaser_extender_task is None:
            self._leaser_extender_task = asyncio.create_task(
                self._leaser_extender()
            )

        if self._unacked_msg_flush_poller_task is None:
            self._unacked_msg_flush_poller_task = asyncio.create_task(
                self._unacked_msg_flush_poller()
            )

        return None

    def close(self) -> None:
        # Don't close until all pending requests end
        self._state.pending_request_count.on_value(0, super().close)

    async def closed(self) -> None:
        await super().closed()
        await asyncio.gather(*[t for _, t in self._pending_requests.get_all()])
        self._pending_requests.clear()

        if self._leaser_extender_task is not None:
            # Force lease extension to stop
            self._leaser_extender_task.cancel()
            try:
                await self._leaser_extender_task
            except asyncio.CancelledError:
                # This is expected since the task is likely calling
                # `asyncio.sleep` after cancellation.
                pass

        if self._unacked_msg_flush_poller_task is not None:
            # Force unacked message flush to stop
            self._unacked_msg_flush_poller_task.cancel()
            try:
                await self._unacked_msg_flush_poller_task
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
        elif msg.kind == connect_pb2.GatewayMessageType.WORKER_REPLY_ACK:
            self._handle_worker_reply_ack(msg)

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

        # Store the task.
        task = asyncio.create_task(
            self._execute_request(req_data, comm_handler)
        )
        self._pending_requests.add(req_data.request_id, req_data, task)

        # Remove the task when it completes.
        task.add_done_callback(
            lambda _: self._pending_requests.pop(req_data.request_id)
        )

    async def _execute_request(
        self,
        req_data: connect_pb2.GatewayExecutorRequestData,
        comm_handler: comm_lib.CommHandler,
    ) -> None:
        """
        Execute a single function request.

        This method handles the full execution lifecycle:
            1. Send WORKER_REQUEST_ACK to confirm receipt
            2. Execute the function via the CommHandler
            3. Send WORKER_REPLY with execution result
        """

        ws = await self._state.ws.wait_for_not_none()
        err = await ws_utils.safe_send(
            self._logger,
            self._state,
            ws,
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
            ).SerializeToString(),
        )
        if err is None:
            comm_res = await comm_handler.post(
                comm_lib.CommRequest(
                    body=req_data.request_payload,
                    headers={},
                    is_connect=True,
                    public_path=None,
                    query_params={
                        server_lib.QueryParamKey.FUNCTION_ID.value: req_data.function_slug,
                    },
                    raw_request=req_data,
                    request_url="",
                    serve_origin=None,
                    serve_path=None,
                )
            )
        else:
            self._logger.error("Execution failed", extra={"error": str(err)})
            comm_res = comm_lib.CommResponse.from_error(self._logger, err)

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

        reply_payload = connect_pb2.SDKResponse(
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
        ).SerializeToString()

        # Add the reply to the buffer in case we need to flush it later.
        self._buffer.add(req_data.request_id, reply_payload)

        self._logger.debug("Sending execution reply")
        err = await ws_utils.safe_send(
            self._logger,
            self._state,
            ws,
            connect_pb2.ConnectMessage(
                kind=connect_pb2.GatewayMessageType.WORKER_REPLY,
                payload=reply_payload,
            ).SerializeToString(),
        )
        if err is not None:
            self._logger.error(
                "Failed to send execution reply", extra={"error": str(err)}
            )

    def _handle_lease_extend_ack(
        self,
        msg: connect_pb2.ConnectMessage,
    ) -> None:
        req_data = connect_pb2.WorkerRequestExtendLeaseAckData()
        req_data.ParseFromString(msg.payload)

        pending_req = self._pending_requests.get(req_data.request_id)
        if pending_req is None:
            self._logger.error(
                "Received lease extend ack for unknown request",
                extra={"request_id": req_data.request_id},
            )
            return

        if req_data.new_lease_id:
            # Each lease extension ack includes a new lease ID. If we don't use the
            # new lease ID the next time we extend, we'll have a bad time.
            pending_req[0].lease_id = req_data.new_lease_id
        else:
            # A null new_lease_id indicates that the lease extension failed. This can happen
            # if the lease was expired, deleted, or taken over by another worker, so we should
            # stop trying to extend it.
            self._logger.debug(
                "Unable to extend lease",
                extra={"request_id": req_data.request_id},
            )
            # Cancelling the task will trigger the done callback to remove it from
            # the pending requests.
            pending_req[1].cancel()

    def _handle_worker_reply_ack(
        self,
        msg: connect_pb2.ConnectMessage,
    ) -> None:
        """
        Handles a worker reply ack, which indicates that the Inngest Server
        received the execution reply.
        """

        req_data = connect_pb2.WorkerReplyAckData()
        req_data.ParseFromString(msg.payload)

        self._logger.debug(
            "Received worker reply ack",
            extra={"request_id": req_data.request_id},
        )
        self._buffer.delete(req_data.request_id)

    async def _leaser_extender(self) -> None:
        while self.closed_event.is_set() is False:
            ws = await self._state.ws.wait_for_not_none()
            extend_lease_interval = (
                await self._state.extend_lease_interval.wait_for_not_none()
            )

            await asyncio.sleep(extend_lease_interval)

            if self._pending_requests.count() == 0:
                continue

            self._logger.debug(
                "Extending leases",
                extra={"count": self._pending_requests.count()},
            )

            for req_data, _ in self._pending_requests.get_all():
                err = await ws_utils.safe_send(
                    self._logger,
                    self._state,
                    ws,
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
                    ).SerializeToString(),
                )
                if err is not None:
                    self._logger.error(
                        "Failed to extend lease", extra={"error": str(err)}
                    )

    async def _unacked_msg_flush_poller(self) -> None:
        """
        Responsible for flushing unacked messages via HTTP. Checks for flushable
        messages on an interval.
        """

        # How long a message should exist before being flushed. We picked the
        # lease interval, but there may be a better value.
        flush_ttl = await self._state.extend_lease_interval.wait_for_not_none()

        while self.closed_event.is_set() is False:
            for request_id, reply_msg in self._buffer.get_older_than(flush_ttl):
                try:
                    err = await self._flush_message(reply_msg)
                    if err is not None:
                        self._logger.error(
                            "Failed to flush message", extra={"error": str(err)}
                        )
                finally:
                    # We only attempt to flush once, so we can delete the
                    # message.
                    self._buffer.delete(request_id)

            await asyncio.sleep(1)

    async def _flush_message(self, msg: bytes) -> types.MaybeError[None]:
        """
        Flush a single message via HTTP.
        """

        url = urllib.parse.urljoin(self._api_origin, "/v0/connect/flush")

        res = await net.fetch_with_auth_fallback(
            self._http_client,
            self._http_client_sync,
            httpx.Request(
                content=msg,
                extensions={
                    "timeout": httpx.Timeout(5).as_dict(),
                },
                headers={
                    "content-type": "application/protobuf",
                },
                method="POST",
                url=url,
            ),
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if isinstance(res, Exception):
            return res
        if res.status_code == 401 or res.status_code == 403:
            return Exception("unauthorized")
        if res.status_code < 200 or res.status_code >= 300:
            return Exception(f"unexpected status code: {res.status_code}")

        return None
