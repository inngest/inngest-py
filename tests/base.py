import asyncio
import time
from typing import Callable
from unittest import IsolatedAsyncioTestCase

import requests
import inngest

from .dev_server import dev_server
from .http_proxy import HTTPProxy
from .net import HOST


class BaseState:
    def is_done(self) -> bool:
        raise NotImplementedError()


class FrameworkTestCase(IsolatedAsyncioTestCase):
    _client: inngest.Inngest
    _dev_server_port: int
    _http_proxy: HTTPProxy

    @classmethod
    def setUpClass(cls) -> None:
        cls._dev_server_port = dev_server.port

        cls._client = inngest.Inngest(
            base_url=f"http://{HOST}:{cls._dev_server_port}",
            id="test",
        )

        cls._http_proxy = HTTPProxy(cls.on_request).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._http_proxy.stop()

    @classmethod
    def on_request(
        cls,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> None:
        raise NotImplementedError()

    @classmethod
    def register(cls) -> None:
        res = requests.put(
            f"http://{cls._http_proxy.host}:{cls._http_proxy.port}/api/inngest",
            timeout=5,
        )
        assert res.status_code == 200

    async def wait_for(
        self,
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

            await asyncio.sleep(0.2)
