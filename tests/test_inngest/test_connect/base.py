from __future__ import annotations

import dataclasses
import typing
import unittest

import httpx
import pytest
import test_core
import test_core.http_proxy
import test_core.ws_proxy
from inngest.experimental.connect import connect_pb2


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
            "ws://0.0.0.0:8289/v0/connect"
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
                url=f"http://0.0.0.0:8288{path}",
            )

            start_resp = connect_pb2.StartResponse()
            start_resp.ParseFromString(resp.content)
            start_resp.gateway_endpoint = ws_proxy.url

            resp_body = start_resp.SerializeToString()
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
