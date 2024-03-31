import dataclasses
import json
import typing
import unittest

import flask
import flask.logging
import flask.testing
import pytest

import inngest
import inngest.flask
from inngest._internal import const, errors

from . import base, cases, dev_server, http_proxy, net

_framework = "flask"
_dev_server_origin = f"http://{net.HOST}:{dev_server.PORT}"

_client = inngest.Inngest(
    api_base_url=_dev_server_origin,
    app_id=_framework,
    event_api_base_url=_dev_server_origin,
    is_production=False,
)

_cases = cases.create_sync_cases(_client, _framework)
_fns: list[inngest.Function] = []
for case in _cases:
    if isinstance(case.fn, list):
        _fns.extend(case.fn)
    else:
        _fns.append(case.fn)


class TestFunctions(unittest.TestCase):
    app: flask.testing.FlaskClient
    client: inngest.Inngest
    dev_server_port: int
    proxy: http_proxy.Proxy

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        app = flask.Flask(__name__)
        cls.client = _client

        inngest.flask.serve(
            app,
            cls.client,
            _fns,
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
        body: typing.Optional[bytes],
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
    setattr(TestFunctions, test_name, case.run_test)


class TestServe(unittest.TestCase):
    def test_cloud_mode_without_signing_key(self) -> None:
        """
        When in Cloud mode but no signing key, raise an error.

        This test isn't needed for every framework since it's testing logic in
        CommHandler
        """

        app = flask.Flask(__name__)
        client = inngest.Inngest(app_id="client")

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        def fn(ctx: inngest.Context, step: inngest.StepSync) -> None:
            pass

        with pytest.raises(Exception) as err:
            inngest.flask.serve(app, client, [fn])
        assert isinstance(err.value, errors.SigningKeyMissingError)


class TestRegistration(unittest.TestCase):
    def test_sync_with_server_kind_mismatch(self) -> None:
        """Ensure that Dev Server cannot initiate a registration request when in
        production mode.
        """
        client = inngest.Inngest(
            app_id=f"{_framework}_registration",
            event_key="test",
            signing_key="signkey-prod-0486c9",
        )

        @client.create_function(
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
        assert body["code"] == const.ErrorCode.SERVER_KIND_MISMATCH.value

    def test_sync_to_cloud_branch_env(self) -> None:
        """
        Test that the SDK correctly syncs itself with Cloud when using a branch
        environment.

        We need to use a mock Cloud since the Dev Server doesn't have a mode
        that simulates Cloud.
        """

        @dataclasses.dataclass
        class State:
            headers: dict[str, list[str]]

        state = State(headers={})

        def on_request(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> http_proxy.Response:
            for k, v in headers.items():
                state.headers[k] = v

            return http_proxy.Response(
                body=json.dumps({}).encode("utf-8"),
                headers={},
                status_code=200,
            )

        mock_cloud = http_proxy.Proxy(on_request).start()
        self.addCleanup(mock_cloud.stop)

        client = inngest.Inngest(
            api_base_url=f"http://localhost:{mock_cloud.port}",
            app_id="my-app",
            env="my-env",
            signing_key="signkey-branch-123abc",
        )

        @client.create_function(
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
        )
        flask_client = app.test_client()
        res = flask_client.put("/api/inngest")
        assert res.status_code == 200
        assert state.headers.get("Authorization") is not None
        assert state.headers.get("X-Inngest-Env") == ["my-env"]
        assert state.headers.get("X-Inngest-Framework") == ["flask"]
        assert state.headers.get("X-Inngest-SDK") == [
            f"inngest-py:v{const.VERSION}"
        ]


if __name__ == "__main__":
    unittest.main()
