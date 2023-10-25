from typing import Protocol

import requests

from .http_proxy import HTTPProxy, Response
from .net import HOST


class _FrameworkTestCase(Protocol):
    dev_server_port: int
    http_proxy: HTTPProxy

    def on_proxy_request(
        self,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> Response:
        ...


def register(app_port: int) -> None:
    res = requests.put(
        f"http://{HOST}:{app_port}/api/inngest",
        timeout=5,
    )
    assert res.status_code == 200


def set_up(case: _FrameworkTestCase) -> None:
    case.http_proxy = HTTPProxy(case.on_proxy_request).start()


def tear_down(case: _FrameworkTestCase) -> None:
    case.http_proxy.stop()
