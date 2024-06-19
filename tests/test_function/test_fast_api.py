import threading
import unittest

import fastapi
import fastapi.testclient
import uvicorn

import inngest
import inngest.fast_api
from inngest._internal import server_lib
from tests import base, dev_server, net

from . import cases

_framework = server_lib.Framework.FAST_API
_app_id = f"{_framework.value}-functions"

_client = inngest.Inngest(
    api_base_url=dev_server.origin,
    app_id=_app_id,
    event_api_base_url=dev_server.origin,
    is_production=False,
)

_cases = cases.create_async_cases(_client, _framework)
_fns: list[inngest.Function] = []
for case in _cases:
    if isinstance(case.fn, list):
        _fns.extend(case.fn)
    else:
        _fns.append(case.fn)


class TestFunctions(unittest.IsolatedAsyncioTestCase):
    client = _client
    app_thread: threading.Thread

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        port = net.get_available_port()

        def start_app() -> None:
            app = fastapi.FastAPI()
            inngest.fast_api.serve(
                app,
                _client,
                _fns,
            )
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

        # Start FastAPI in a thread instead of using their test client, since
        # their test client doesn't seem to actually run requests in parallel
        # (this is evident in the flakiness of our asyncio race test). If we fix
        # this issue, we can go back to their test client
        cls.app_thread = threading.Thread(daemon=True, target=start_app)
        cls.app_thread.start()
        base.register(port)

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        cls.app_thread.join(timeout=1)


for case in _cases:
    test_name = f"test_{case.name}"
    setattr(TestFunctions, test_name, case.run_test)


if __name__ == "__main__":
    unittest.main()
