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

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        dev_server_origin = f"http://{net.HOST}:{dev_server.PORT}"
        app = flask.Flask(__name__)
        cls.client = inngest.Inngest(
            app_id="flask",
            event_api_base_url=dev_server_origin,
        )

        inngest.flask.serve(
            app,
            cls.client,
            [case.fn for case in _cases],
            api_base_url=dev_server_origin,
        )
        cls.app = app.test_client()
        cls.proxy = http_proxy.Proxy(cls.on_proxy_request).start()
        base.register(cls.proxy.port)

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        cls.proxy.stop()

    @classmethod
    def on_proxy_request(
        cls,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> http_proxy.Response:
        res = cls.app.open(
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
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> None:
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
