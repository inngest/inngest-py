import unittest

import flask
import flask.testing

import inngest
import inngest.flask

from . import base, cases, dev_server, http_proxy, net

_client = inngest.Inngest(
    app_id="flask",
    base_url=f"http://{net.HOST}:{dev_server.PORT}",
)

_cases = cases.create_cases(_client, "flask")


class TestFlask(unittest.TestCase):
    app: flask.testing.FlaskClient
    dev_server_port: int
    proxy: http_proxy.Proxy

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        app = flask.Flask(__name__)
        app.logger.disabled = True
        inngest.flask.serve(
            app,
            _client,
            [case.fn for case in _cases],
        )
        cls.app = app.test_client()

    def setUp(self) -> None:
        super().setUp()
        base.set_up(self)
        base.register(self.proxy.port)

    def tearDown(self) -> None:
        super().tearDown()
        base.tear_down(self)

    def on_proxy_request(
        self,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> http_proxy.Response:
        res = self.app.open(
            method=method,
            path=path,
            headers=headers,
            data=body,
        )

        return http_proxy.Response(
            body=res.data,
            headers=dict(res.headers),
            status_code=res.status_code,
        )


for case in _cases:
    test_name = f"test_{case.name}"
    setattr(TestFlask, test_name, case.run_test)

if __name__ == "__main__":
    unittest.main()
