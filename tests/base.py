import typing

import httpx

from . import http_proxy, net


class _FrameworkTestCase(typing.Protocol):
    dev_server_port: int
    proxy: http_proxy.Proxy

    def on_proxy_request(
        self,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> http_proxy.Response:
        ...


def register(app_port: int) -> None:
    res = httpx.put(
        f"http://{net.HOST}:{app_port}/api/inngest",
        timeout=5,
    )
    assert res.status_code == 200


def set_up(case: _FrameworkTestCase) -> None:
    case.proxy = http_proxy.Proxy(case.on_proxy_request).start()


def tear_down(case: _FrameworkTestCase) -> None:
    case.proxy.stop()
