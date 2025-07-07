import typing
import unittest

import flask
import flask.testing
import inngest
import inngest.digital_ocean
from inngest._internal import server_lib
from inngest.experimental import dev_server, digital_ocean_simulator
from test_core import base, http_proxy

from . import cases
from .cases.base import Case

_framework = server_lib.Framework.DIGITAL_OCEAN
_app_id = f"{_framework.value}-functions"

_client = inngest.Inngest(
    api_base_url=dev_server.server.origin,
    app_id=_app_id,
    event_api_base_url=dev_server.server.origin,
    is_production=False,
)

_cases: list[Case] = []
for case in cases.create_sync_cases(_client, _framework):
    if case.name == "batch_that_needs_api":
        # Skip because the test is flakey for DigitalOcean for some reason
        continue

    _cases.append(case)

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
        main = inngest.digital_ocean.serve(
            _client,
            _fns,
        )
        cls.app = digital_ocean_simulator.DigitalOceanSimulator(
            main
        ).app.test_client()
        cls.client = _client
        cls.proxy = http_proxy.Proxy(cls.on_proxy_request).start()
        base.register(cls.proxy.port, digital_ocean_simulator.FULL_PATH)

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
