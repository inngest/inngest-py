import asyncio
import threading
import time
from typing import Callable
from unittest import IsolatedAsyncioTestCase


from flask import Flask
from flask.testing import FlaskClient
import requests
import inngest

from .http_proxy import HTTPProxy


foo = 0


@inngest.create_function(
    inngest.FunctionOpts(id="foo"),
    inngest.TriggerEvent(event="app/foo"),
)
def _foo(**_kwargs: object) -> None:
    global foo
    foo += 1


_app = Flask(__name__)
_client = inngest.Inngest(id="test")
inngest.flask.serve(
    _app,
    _client,
    [_foo],
)


class TestFlask(IsolatedAsyncioTestCase):
    _app: FlaskClient
    _client: inngest.Inngest
    _http_proxy: HTTPProxy
    _server_thread: threading.Thread

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _app.test_client()
        cls._client = _client

        def on_request(
            *,
            body: bytes | None,
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> None:
            cls._app.open(
                method=method,
                path=path,
                headers=headers,
                data=body,
            )

        cls._http_proxy = HTTPProxy(on_request).start()

        # Register
        res = requests.put("http://localhost:9000/api/inngest", timeout=5)
        assert res.status_code == 200

    @classmethod
    def tearDownClass(cls) -> None:
        print("bye")
        cls._http_proxy.stop()

    async def wait_for(
        self,
        assertion: Callable[[], None],
        timeout=5,
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

            await asyncio.sleep(0.1)

    async def test_foo(self) -> None:
        self._client.send(inngest.Event(name="app/foo"))

        def assertion() -> None:
            assert foo == 1

        await self.wait_for(assertion)
