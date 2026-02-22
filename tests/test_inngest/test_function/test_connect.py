import asyncio
import threading
import typing
import unittest

import inngest
import test_core
from inngest._internal import server_lib
from inngest.connect import ConnectionState, connect
from inngest.connect._internal.connection import (
    WorkerConnection,
    WorkerConnectionImpl,
)
from inngest.experimental import dev_server

from test_inngest.test_function import cases

_framework = server_lib.Framework.CONNECT
_app_id = test_core.worker_suffix(f"{_framework.value}-functions")

_client = inngest.Inngest(
    api_base_url=dev_server.server.origin,
    app_id=_app_id,
    event_api_base_url=dev_server.server.origin,
    is_production=False,
)

_cases = cases.create_async_cases(_client, _framework)
_fns: list[inngest.Function[typing.Any]] = []
for case in _cases:
    if isinstance(case.fn, list):
        _fns.extend(case.fn)
    else:
        _fns.append(case.fn)


class TestFunctions(unittest.IsolatedAsyncioTestCase):
    client = _client
    conn: WorkerConnection
    _conn_ready: threading.Event
    _conn_thread: threading.Thread

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.conn = connect([(cls.client, _fns)])
        cls._conn_ready = threading.Event()

        def run_connection() -> None:
            async def _run() -> None:
                task = asyncio.create_task(cls.conn.start())
                await cls.conn.wait_for_state(ConnectionState.ACTIVE)
                cls._conn_ready.set()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            asyncio.run(_run())

        cls._conn_thread = threading.Thread(daemon=True, target=run_connection)
        cls._conn_thread.start()
        cls._conn_ready.wait(timeout=30)

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        if isinstance(cls.conn, WorkerConnectionImpl):
            cls.conn._close()
            cls._conn_thread.join(timeout=5)


for case in _cases:
    test_name = f"test_{case.name}"
    setattr(TestFunctions, test_name, case.run_test)


if __name__ == "__main__":
    unittest.main()
