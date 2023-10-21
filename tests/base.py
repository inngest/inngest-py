import os
import time
from typing import Callable, Protocol, Type

import requests

import inngest

from .dev_server import dev_server
from .http_proxy import HTTPProxy
from .net import HOST


class BaseState:
    def is_done(self) -> bool:
        raise NotImplementedError()


class FrameworkTestCase(Protocol):
    client: inngest.Inngest
    dev_server_port: int
    http_proxy: HTTPProxy

    def on_proxy_request(
        self,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> None:
        ...


def register(app_port: int) -> None:
    res = requests.put(
        f"http://{HOST}:{app_port}/api/inngest",
        timeout=5,
    )
    assert res.status_code == 200


def set_up(case: FrameworkTestCase) -> None:
    case.http_proxy = HTTPProxy(case.on_proxy_request).start()


def set_up_class(case: Type[FrameworkTestCase]) -> None:
    case.dev_server_port = int(os.getenv("DEV_SERVER_PORT") or dev_server.port)

    case.client = inngest.Inngest(
        base_url=f"http://{HOST}:{case.dev_server_port}",
        id=case.__name__,
    )


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
