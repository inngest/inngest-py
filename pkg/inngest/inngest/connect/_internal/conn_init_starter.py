import asyncio
import datetime
import typing
import urllib.parse

import httpx

from inngest._internal import net, server_lib, types

from . import connect_pb2
from .base_handler import _BaseHandler
from .errors import _NonRetryableError
from .models import ConnectionState, _State

_max_attempts = 5
_reconnect_interval = datetime.timedelta(seconds=5)


class _ConnInitHandler(_BaseHandler):
    """
    Starts the connection by sending the "start request" to the REST API.
    """

    _closed_event: typing.Optional[asyncio.Event] = None
    _initial_request_task: typing.Optional[asyncio.Task[None]] = None
    _reconnect_watcher_task: typing.Optional[asyncio.Task[None]] = None

    @property
    def closed_event(self) -> asyncio.Event:
        if self._closed_event is None:
            self._closed_event = asyncio.Event()
        return self._closed_event

    def __init__(
        self,
        *,
        api_origin: str,
        env: typing.Optional[str],
        http_client: net.ThreadAwareAsyncHTTPClient,
        http_client_sync: httpx.Client,
        logger: types.Logger,
        rewrite_gateway_endpoint: typing.Optional[typing.Callable[[str], str]],
        signing_key: typing.Optional[str],
        signing_key_fallback: typing.Optional[str],
        state: _State,
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
        err: typing.Optional[Exception] = None

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
                attempts < _max_attempts and self.closed_event.is_set() is False
            ):
                if attempts == 0:
                    self._logger.debug(
                        "ConnectionStart request send",
                        extra={"url": url},
                    )
                else:
                    await asyncio.sleep(_reconnect_interval.seconds)
                    self._logger.debug(
                        "ConnectionStart request retry",
                        extra={"url": url},
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
                        raise _NonRetryableError("unauthorized")
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

                    self._state.conn_init.value = (
                        connect_pb2.AuthData(
                            session_token=start_resp.session_token,
                            sync_token=start_resp.sync_token,
                        ),
                        final_endpoint,
                    )

                    break
                except _NonRetryableError as e:
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
