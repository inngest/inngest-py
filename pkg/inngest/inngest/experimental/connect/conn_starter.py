import asyncio
import datetime
import typing
import urllib.parse

import httpx

from inngest._internal import net, types

from . import connect_pb2
from .errors import _NonRetryableError
from .models import ConnectionState, _State

_max_attempts = 10
_reconnect_interval = datetime.timedelta(seconds=5)


class _ConnStarter:
    """
    Starts the connection by sending the "start request" to the REST API.
    """

    _closed_event: typing.Optional[asyncio.Event] = None
    _initial_request_sent: bool = False
    _watcher_task: typing.Optional[asyncio.Task[None]] = None

    def __init__(
        self,
        api_origin: str,
        http_client: net.ThreadAwareAsyncHTTPClient,
        http_client_sync: httpx.Client,
        logger: types.Logger,
        rewrite_gateway_endpoint: typing.Optional[typing.Callable[[str], str]],
        signing_key: typing.Optional[str],
        signing_key_fallback: typing.Optional[str],
        state: _State,
    ):
        self._api_origin = api_origin
        self._http_client = http_client
        self._http_client_sync = http_client_sync
        self._logger = logger
        self._rewrite_gateway_endpoint = rewrite_gateway_endpoint
        self._signing_key = signing_key
        self._signing_key_fallback = signing_key_fallback
        self._state = state

    async def start(self) -> types.MaybeError[None]:
        if self._closed_event is None:
            self._closed_event = asyncio.Event()

        if self._initial_request_sent is False:
            err = await self._send_start_request()
            if isinstance(err, Exception):
                return err
            self._initial_request_sent = True

        if self._watcher_task is None:
            self._watcher_task = asyncio.create_task(
                self._watcher(self._closed_event)
            )

        return None

    async def stop(self) -> None:
        if self._closed_event is not None:
            self._closed_event.set()

        if self._watcher_task is not None:
            self._watcher_task.cancel()

    async def _send_start_request(self) -> types.MaybeError[None]:
        self._state.conn_state.value = ConnectionState.CONNECTING

        req = connect_pb2.StartRequest(
            exclude_gateways=self._state.exclude_gateways,
        )

        attempts = 0
        err: typing.Optional[Exception] = None
        while attempts < _max_attempts:
            if attempts == 0:
                self._logger.debug("ConnectionStart request send")
            else:
                await asyncio.sleep(_reconnect_interval.seconds)
                self._logger.debug("ConnectionStart request retry")

            try:
                res = await net.fetch_with_auth_fallback(
                    self._http_client,
                    self._http_client_sync,
                    httpx.Request(
                        method="POST",
                        url=urllib.parse.urljoin(
                            self._api_origin, "/v0/connect/start"
                        ),
                        content=req.SerializeToString(),
                        headers={
                            "content-type": "application/protobuf",
                        },
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
                self._logger.debug("ConnectionStart response received")

                start_resp = connect_pb2.StartResponse()
                start_resp.ParseFromString(res.content)

                self._state.auth_data = connect_pb2.AuthData(
                    session_token=start_resp.session_token,
                    sync_token=start_resp.sync_token,
                )
                self._state.conn_id = start_resp.connection_id
                self._connection_id = start_resp.connection_id

                final_endpoint = start_resp.gateway_endpoint
                if self._rewrite_gateway_endpoint:
                    final_endpoint = self._rewrite_gateway_endpoint(
                        final_endpoint
                    )
                self._state.gateway_url = final_endpoint
                return None
            except _NonRetryableError as e:
                return e
            except Exception as e:
                err = e

                if attempts < _max_attempts:
                    self._logger.error(
                        "ConnectionStart request failed",
                        extra={"error": str(err)},
                    )
            finally:
                attempts += 1

        return err

    async def _watcher(self, closed_event: asyncio.Event) -> None:
        while closed_event.is_set() is False:
            # Only send start requests when the connection is reconnecting.
            if self._state.conn_state.value != ConnectionState.RECONNECTING:
                await self._state.conn_state.wait_for(
                    ConnectionState.RECONNECTING
                )

            err = await self._send_start_request()
            if isinstance(err, Exception):
                self._logger.error(
                    "ConnectionStart request failed",
                    extra={"error": str(err)},
                )
                await self.stop()

            await asyncio.sleep(_reconnect_interval.seconds)
