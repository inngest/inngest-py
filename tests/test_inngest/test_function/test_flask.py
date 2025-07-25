import typing
import unittest

import flask
import flask.testing
import inngest
import inngest.flask
from inngest._internal import server_lib
from inngest.experimental import dev_server
from test_core import base, http_proxy

from . import cases

_framework = server_lib.Framework.FLASK
_app_id = f"{_framework.value}-functions"

_client = inngest.Inngest(
    api_base_url=dev_server.server.origin,
    app_id=_app_id,
    event_api_base_url=dev_server.server.origin,
    is_production=False,
)

_cases = cases.create_sync_cases(_client, _framework)
_fns: list[inngest.Function[typing.Any]] = []
for case in _cases:
    if isinstance(case.fn, list):
        _fns.extend(case.fn)
    else:
        _fns.append(case.fn)


class TestFunctions(unittest.IsolatedAsyncioTestCase):
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
        return http_proxy.on_proxy_flask_request(
            cls.app,
            body=body,
            headers=headers,
            method=method,
            path=path,
        )


for case in _cases:
    test_name = f"test_{case.name}"
    setattr(TestFunctions, test_name, case.run_test)


if __name__ == "__main__":
    unittest.main()
