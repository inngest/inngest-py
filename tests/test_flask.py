import unittest

from flask import Flask
from flask.testing import FlaskClient

import inngest

from .base import FrameworkTestCase, register, set_up, tear_down
from .cases import create_cases
from .dev_server import dev_server_port
from .http_proxy import HTTPProxy, Response
from .net import HOST

_client = inngest.Inngest(
    base_url=f"http://{HOST}:{dev_server_port}",
    id="flask",
)

_cases = create_cases(_client, "flask")


class TestFlask(unittest.TestCase, FrameworkTestCase):
    app: FlaskClient
    dev_server_port: int
    http_proxy: HTTPProxy

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        app = Flask(__name__)
        app.logger.disabled = True
        inngest.flask.serve(
            app,
            _client,
            [case.fn for case in _cases],
        )
        cls.app = app.test_client()

    def setUp(self) -> None:
        super().setUp()
        set_up(self)
        register(self.http_proxy.port)

    def tearDown(self) -> None:
        super().tearDown()
        tear_down(self)

    def on_proxy_request(
        self,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> Response:
        res = self.app.open(
            method=method,
            path=path,
            headers=headers,
            data=body,
        )

        return Response(
            body=res.data,
            headers={k: v for k, v in res.headers},
            status_code=res.status_code,
        )


for case in _cases:
    test_name = f"test_{case.name}"
    setattr(TestFlask, test_name, case.run_test)

if __name__ == "__main__":
    unittest.main()
