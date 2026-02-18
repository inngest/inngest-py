import asyncio
import typing
import urllib.parse

import httpx

from inngest._internal import net, server_lib, types

from . import connect_pb2
from .base_handler import BaseHandler
from .consts import CONN_INIT_RETRY_INTERVAL_SEC, MAX_CONN_INIT_ATTEMPTS
from .errors import NonRetryableError
from .models import ConnectionState, State


class ConnInitHandler(BaseHandler):
    """
    Bootstraps the connection by making a REST call to /v0/connect/start.

    The server responds with:
        - connection_id: Unique identifier for this connection
        - gateway_endpoint: WebSocket URL to connect to
        - session_token/sync_token: Authentication tokens for the WebSocket

    Retry Behavior:
        - Max attempts: Configurable via MAX_CONN_INIT_ATTEMPTS
        - Retry interval: Configurable via CONN_INIT_RETRY_INTERVAL_SEC
        - Non-retryable errors (e.g., 401/403) cause immediate failure

    State Ownership:
        This handler sets:
        - conn_id: The connection ID from the server response
        - conn_init: Tuple of (AuthData, gateway_endpoint)
        - fatal_error: Set on non-retryable errors
        - conn_state: Set to CONNECTING when starting

    Reconnection:
        The handler watches for RECONNECTING state and re-sends the start
        request when triggered. The exclude_gateways list allows avoiding
        problematic gateways on reconnect.
    """

    _closed_event: asyncio.Event | None = None
    _initial_request_task: asyncio.Task[None] | None = None
    _reconnect_watcher_task: asyncio.Task[None] | None = None

    @property
    def closed_event(self) -> asyncio.Event:
        if self._closed_event is None:
            self._closed_event = asyncio.Event()
        return self._closed_event

    def __init__(
        self,
        *,
        api_origin: str,
        env: str | None,
        http_client: net.ThreadAwareAsyncHTTPClient,
        http_client_sync: httpx.Client,
        logger: types.Logger,
        rewrite_gateway_endpoint: typing.Callable[[str], str] | None,
        signing_key: str | None,
        signing_key_fallback: str | None,
        state: State,
    ):
        self._api_origin = api_origin
        self._env = env
        self._http_client = http_client
        self._http_client_sync = http_client_sync
        self._logger = logger
        self._rewrite_gateway_endpoint = rewrite_gateway_endpoint
        self._signing_key = signing_key
        self._signing_key_fallback = signing_key_fallback
        self._state = state

    def start(self) -> types.MaybeError[None]:
        if self._closed_event is None:
            self._closed_event = asyncio.Event()

        if self._initial_request_task is None:
            self._initial_request_task = asyncio.create_task(
                self._send_start_request()
            )

        if self._reconnect_watcher_task is None:
            self._reconnect_watcher_task = asyncio.create_task(
                self._reconnect_watcher(self._closed_event)
            )

        return None

    def close(self) -> None:
        self.closed_event.set()

        if self._reconnect_watcher_task is not None:
            self._reconnect_watcher_task.cancel()

    async def closed(self) -> None:
        await self.closed_event.wait()

        if self._reconnect_watcher_task is not None:
            try:
                await self._reconnect_watcher_task
            except asyncio.CancelledError:
                # Expected.
                pass

    async def _send_start_request(self) -> None:
        err: Exception | None = None

        while self.closed_event.is_set() is False:
            if err is not None:
                # Close everything because we non-retryably failed to send the
                # start request.
                self._state.fatal_error.value = err
                return

            await self._state.conn_init.wait_for(None)
            if self._state.conn_state.value in [
                ConnectionState.CLOSED,
                ConnectionState.CLOSING,
            ]:
                return

            self._state.conn_state.value = ConnectionState.CONNECTING

            req = connect_pb2.StartRequest(
                exclude_gateways=self._state.exclude_gateways,
            )

            url = urllib.parse.urljoin(self._api_origin, "/v0/connect/start")

            attempts = 0
            while (
                attempts < MAX_CONN_INIT_ATTEMPTS
                and self.closed_event.is_set() is False
            ):
                if attempts == 0:
                    self._logger.debug(
                        "ConnectionStart request send",
                        extra={"url": url},
                    )
                else:
                    await asyncio.sleep(CONN_INIT_RETRY_INTERVAL_SEC)
                    self._logger.debug(
                        "ConnectionStart request retry",
                        extra={
                            "error": str(err),
                            "url": url,
                        },
                    )

                headers = {
                    "content-type": "application/protobuf",
                }
                if self._env:
                    headers[server_lib.HeaderKey.ENV.value] = self._env

                try:
                    res = await net.fetch_with_auth_fallback(
                        self._http_client,
                        self._http_client_sync,
                        httpx.Request(
                            content=req.SerializeToString(),
                            extensions={
                                "timeout": httpx.Timeout(5).as_dict(),
                            },
                            headers=headers,
                            method="POST",
                            url=url,
                        ),
                        signing_key=self._signing_key,
                        signing_key_fallback=self._signing_key_fallback,
                    )
                    if isinstance(res, Exception):
                        raise res
                    if res.status_code == 401 or res.status_code == 403:
                        raise NonRetryableError("unauthorized")
                    if res.status_code != 200:
                        raise Exception(
                            f"failed to send start request: {res.status_code}"
                        )

                    # Clear the error since we got a successful response. Err is
                    # set if this was a retry.
                    err = None

                    start_resp = connect_pb2.StartResponse()
                    start_resp.ParseFromString(res.content)
                    self._logger.debug(
                        "ConnectionStart response received",
                        extra={
                            "connection_id": start_resp.connection_id,
                            "gateway_endpoint": start_resp.gateway_endpoint,
                            "gateway_group": start_resp.gateway_group,
                        },
                    )

                    self._state.conn_id = start_resp.connection_id

                    final_endpoint = start_resp.gateway_endpoint
                    if self._rewrite_gateway_endpoint:
                        final_endpoint = self._rewrite_gateway_endpoint(
                            final_endpoint
                        )

                    err = validate_gateway_endpoint(final_endpoint)
                    if isinstance(err, Exception):
                        raise err

                    self._state.conn_init.value = (
                        connect_pb2.AuthData(
                            session_token=start_resp.session_token,
                            sync_token=start_resp.sync_token,
                        ),
                        final_endpoint,
                    )

                    break
                except NonRetryableError as e:
                    err = e
                    break
                except Exception as e:
                    err = e
                finally:
                    attempts += 1

            if err is not None:
                self._logger.error(
                    "ConnectionStart request failed",
                    extra={"error": str(err)},
                )

    async def _reconnect_watcher(self, closed_event: asyncio.Event) -> None:
        while closed_event.is_set() is False:
            await self._state.conn_state.wait_for(
                ConnectionState.RECONNECTING,
                immediate=False,
            )


def validate_gateway_endpoint(endpoint: str) -> types.MaybeError[None]:
    if endpoint.strip() == "":
        return Exception("gateway endpoint is empty")

    try:
        parsed = urllib.parse.urlparse(endpoint)
    except Exception as e:
        return e

    valid_schemes = ["ws", "wss"]
    if parsed.scheme not in valid_schemes:
        return Exception(
            f"gateway endpoint scheme {parsed.scheme} is not valid, must be one of {', '.join(valid_schemes)}"
        )

    if parsed.hostname is None:
        return Exception("gateway endpoint hostname is required")

    return None
