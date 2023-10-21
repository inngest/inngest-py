import time
from typing import Callable, Protocol

import requests

from .http_proxy import HTTPProxy, Response
from .net import HOST


class FrameworkTestCase(Protocol):
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


def set_up(case: FrameworkTestCase) -> None:
    case.http_proxy = HTTPProxy(case.on_proxy_request).start()


def tear_down(case: FrameworkTestCase) -> None:
    case.http_proxy.stop()


def wait_for(
    assertion: Callable[[], None],
    timeout: int = 5,
) -> None:
    start = time.time()
    while True:
        try:
            assertion()
            return
        except Exception as err:
            timed_out = time.time() - start > timeout
            if timed_out:
                raise err

        time.sleep(0.2)
