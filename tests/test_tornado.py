import json

import tornado.httpclient
import tornado.log
import tornado.testing
import tornado.web

import inngest
import inngest.tornado
from inngest._internal import const

from . import base, cases, dev_server, http_proxy, net

_cases = cases.create_cases_sync("tornado")


class TestTornado(tornado.testing.AsyncHTTPTestCase):
    app: tornado.web.Application
    client: inngest.Inngest
    dev_server_port: int
    proxy: http_proxy.Proxy

    def get_app(self) -> tornado.web.Application:
        return self.app

    def setUp(self) -> None:
        # Set self.app before calling parent setUp(), since the Tornado test
        # class expects it to be set. Can't set it in setUpClass() because then
        # the same app would be shared between tests.
        self.app = tornado.web.Application()

        super().setUp()
        dev_server_origin = f"http://{net.HOST}:{dev_server.PORT}"
        self.client = inngest.Inngest(
            app_id="tornado",
            event_api_base_url=dev_server_origin,
        )
        inngest.tornado.serve(
            self.app,
            self.client,
            [case.fn for case in _cases],
            api_base_url=dev_server_origin,
        )
        self.proxy = http_proxy.Proxy(self.on_proxy_request).start()

        # TODO: Stop registering on every test
        base.register(self.proxy.port)

    def tearDown(self) -> None:
        super().tearDown()
        self.proxy.stop()

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


class TestTornadoRegistration(tornado.testing.AsyncHTTPTestCase):
    app: tornado.web.Application = tornado.web.Application()

    def get_app(self) -> tornado.web.Application:
        return self.app

    def test_dev_server_to_prod(self) -> None:
        """
        Ensure that Dev Server cannot initiate a registration request when in
        production mode.
        """

        client = inngest.Inngest(
            app_id="tornado",
            event_key="test",
            is_production=True,
        )

        @inngest.create_function(
            fn_id="foo",
            retries=0,
            trigger=inngest.TriggerEvent(event="app/foo"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> None:
            pass

        inngest.tornado.serve(
            self.get_app(),
            client,
            [fn],
            signing_key="signkey-prod-0486c9",
        )
        res = self.fetch(
            "/api/inngest",
            body=json.dumps({}),
            headers={
                const.HeaderKey.SERVER_KIND.value.lower(): const.ServerKind.DEV_SERVER.value,
            },
            method="PUT",
        )
        assert res.code == 400
        body: object = json.loads(res.body)
        assert (
            isinstance(body, dict)
            and body["code"]
            == const.ErrorCode.DISALLOWED_REGISTRATION_INITIATOR.value
        )


if __name__ == "__main__":
    tornado.testing.main()
