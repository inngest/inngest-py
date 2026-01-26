import asyncio
import threading
import typing
import unittest

import inngest
import test_core
from inngest._internal import server_lib
from inngest.connect import ConnectionState, connect
from inngest.connect._internal.connection import WorkerConnection
from inngest.experimental import dev_server

from . import cases

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
    conn_loop: asyncio.AbstractEventLoop
    conn_ready: threading.Event
    conn_thread: threading.Thread

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.conn_ready = threading.Event()

        def run_connection() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            cls.conn_loop = loop

            async def start_conn() -> None:
                conn = connect([(cls.client, _fns)])
                cls.conn = conn
                task = asyncio.create_task(conn.start())
                await conn.wait_for_state(ConnectionState.ACTIVE)
                cls.conn_ready.set()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            loop.run_until_complete(start_conn())

        cls.conn_thread = threading.Thread(daemon=True, target=run_connection)
        cls.conn_thread.start()
        cls.conn_ready.wait(timeout=30)

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        if hasattr(cls, "conn"):
            cls.conn_loop.call_soon_threadsafe(
                lambda: asyncio.create_task(cls.conn.close(wait=True))
            )
        cls.conn_thread.join(timeout=5)


for case in _cases:
    test_name = f"test_{case.name}"
    setattr(TestFunctions, test_name, case.run_test)


if __name__ == "__main__":
    unittest.main()
