import tornado.log
import tornado.testing
import tornado.web

import inngest
import inngest.tornado

from . import base, cases, dev_server, http_proxy, net

_client = inngest.Inngest(
    app_id="tornado",
    base_url=f"http://{net.HOST}:{dev_server.PORT}",
)

_cases = cases.create_cases_sync(_client, "tornado")


class TestTornado(tornado.testing.AsyncHTTPTestCase):
    app: tornado.web.Application
    dev_server_port: int
    proxy: http_proxy.Proxy

    def get_app(self) -> tornado.web.Application:
        return self.app

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.app = tornado.web.Application()
        inngest.tornado.serve(
            cls.app,
            _client,
            [
                case.fn
                for case in _cases
                if isinstance(case.fn, inngest.FunctionSync)
            ],
        )

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
        res = self.fetch(
            path,
            method=method,
            headers={k: v[0] for k, v in headers.items()},
            body=body,
        )

        return http_proxy.Response(
            body=res.body,
            headers=dict(res.headers.items()),
            status_code=res.code,
        )


for case in _cases:
    test_name = f"test_{case.name}"
    setattr(TestTornado, test_name, case.run_test)


if __name__ == "__main__":
    tornado.testing.main()
