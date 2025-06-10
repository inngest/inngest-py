from __future__ import annotations

import dataclasses
import typing
import unittest

import httpx
import pytest
import test_core
import test_core.http_proxy
import test_core.ws_proxy
from inngest.connect import ConnectionState
from inngest.connect._internal import connect_pb2
from inngest.connect._internal.connection import (
    WorkerConnection,
    _WebSocketWorkerConnection,
)
from inngest.experimental.dev_server import dev_server


@dataclasses.dataclass
class _Proxies:
    http_proxy: test_core.http_proxy.Proxy
    requests: list[_Request]
    ws_proxy: test_core.ws_proxy.WebSocketProxy


@dataclasses.dataclass
class _Request:
    body: typing.Optional[bytes]
    headers: dict[str, list[str]]
    method: str
    path: str


@pytest.mark.timeout(5, method="thread")
class BaseTest(unittest.IsolatedAsyncioTestCase):
    async def create_proxies(self) -> _Proxies:
        ws_proxy = test_core.ws_proxy.WebSocketProxy(
            f"ws://0.0.0.0:{dev_server.server.port + 1}/v0/connect"
        )
        self.addCleanup(ws_proxy.stop)
        await ws_proxy.start()

        requests: list[_Request] = []

        def http_proxy_handler(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> test_core.http_proxy.Response:
            requests.append(_Request(body, headers, method, path))

            resp = httpx.request(
                content=body,
                headers={k: v[0] for k, v in headers.items()},
                method=method,
                url=f"http://0.0.0.0:{dev_server.server.port}{path}",
            )

            resp_body = resp.content

            try:
                # Rewrite the gateway endpoint if this is a start response.
                start_resp = connect_pb2.StartResponse()
                start_resp.ParseFromString(resp.content)
                start_resp.gateway_endpoint = ws_proxy.url
                resp_body = start_resp.SerializeToString()
            except Exception:
                pass

            resp_headers = {k: v[0] for k, v in resp.headers.items()}
            resp_headers["content-length"] = str(len(resp_body))

            return test_core.http_proxy.Response(
                body=resp_body,
                headers=resp_headers,
                status_code=resp.status_code,
            )

        http_proxy = test_core.http_proxy.Proxy(http_proxy_handler).start()
        self.addCleanup(http_proxy.stop)

        return _Proxies(
            http_proxy=http_proxy,
            requests=requests,
            ws_proxy=ws_proxy,
        )


def collect_states(conn: WorkerConnection) -> list[ConnectionState]:
    states: list[ConnectionState] = []
    if isinstance(conn, _WebSocketWorkerConnection):
        conn._state.conn_state.on_change(lambda _, state: states.append(state))
    states.append(conn.get_state())
    return states
