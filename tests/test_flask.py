import unittest

import flask
import flask.logging
import flask.testing

import inngest
import inngest.flask
from inngest._internal import const

from . import base, cases, dev_server, http_proxy, net

_cases = cases.create_cases_sync("flask")


class TestFlask(unittest.TestCase):
    app: flask.testing.FlaskClient
    client: inngest.Inngest
    dev_server_port: int
    proxy: http_proxy.Proxy

    def setUp(self) -> None:
        super().setUp()
        app = flask.Flask(__name__)
        self.client = inngest.Inngest(
            app_id="flask",
            base_url=f"http://{net.HOST}:{dev_server.PORT}",
        )

        inngest.flask.serve(
            app,
            self.client,
            [case.fn for case in _cases],
        )
        self.app = app.test_client()
        self.proxy = http_proxy.Proxy(self.on_proxy_request).start()
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


class TestRegistration(unittest.TestCase):
    def test_dev_server_to_prod(self) -> None:
        """Ensure that Dev Server cannot initiate a registration request when in
        production mode.
        """
        client = inngest.Inngest(
            app_id="flask_registration",
            event_key="test",
            is_production=True,
        )

        @inngest.create_function(
            fn_id="foo",
            retries=0,
            trigger=inngest.TriggerEvent(event="app/foo"),
        )
        def fn(**_kwargs: object) -> None:
            pass

        app = flask.Flask(__name__)
        inngest.flask.serve(
            app,
            client,
            [fn],
            signing_key="signkey-prod-0486c9",
        )
        flask_client = app.test_client()
        res = flask_client.put(
            "/api/inngest",
            headers={
                const.HeaderKey.SERVER_KIND.value.lower(): const.ServerKind.DEV_SERVER.value,
            },
        )
        assert res.status_code == 400
        body: object = res.json
        assert isinstance(body, dict)
        assert (
            body["code"]
            == const.ErrorCode.DISALLOWED_REGISTRATION_INITIATOR.value
        )


if __name__ == "__main__":
    unittest.main()
