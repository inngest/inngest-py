import tornado.log
import tornado.testing
from tornado.web import Application

import inngest
import inngest.tornado

from .base import register, set_up, tear_down
from .cases import create_cases
from .dev_server import DEV_SERVER_PORT
from .http_proxy import HTTPProxy, Response
from .net import HOST

_client = inngest.Inngest(
    app_id="tornado",
    base_url=f"http://{HOST}:{DEV_SERVER_PORT}",
)

_cases = create_cases(_client, "tornado")


class TestTornado(tornado.testing.AsyncHTTPTestCase):
    app: Application
    dev_server_port: int
    http_proxy: HTTPProxy

    def get_app(self) -> Application:
        return self.app

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.app = Application()
        inngest.tornado.serve(
            cls.app,
            _client,
            [case.fn for case in _cases],
        )

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
        res = self.fetch(
            path,
            method=method,
            headers={k: v[0] for k, v in headers.items()},
            body=body,
        )

        return Response(
            body=res.body,
            headers=dict(res.headers.items()),
            status_code=res.code,
        )


for case in _cases:
    test_name = f"test_{case.name}"
    setattr(TestTornado, test_name, case.run_test)


if __name__ == "__main__":
    tornado.testing.main()
