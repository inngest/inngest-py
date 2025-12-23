import threading
import typing
import unittest

import flask
import flask.testing
import inngest
import inngest.flask
import test_core
from inngest._internal import server_lib
from inngest.experimental import dev_server
from test_core import base, net

from . import cases

_framework = server_lib.Framework.FLASK
_app_id = test_core.worker_suffix(f"{_framework.value}-functions")

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
    server_thread: threading.Thread

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

        port = net.get_available_port()

        def run_server() -> None:
            app.run(threaded=True, port=port)

        cls.server_thread = threading.Thread(target=run_server)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        base.register(port)

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        cls.server_thread.join(timeout=1)


for case in _cases:
    test_name = f"test_{case.name}"
    setattr(TestFunctions, test_name, case.run_test)


if __name__ == "__main__":
    unittest.main()
