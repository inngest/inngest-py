import asyncio
import os
import threading
import typing
import unittest

import inngest
import test_core
from inngest._internal import const, server_lib
from inngest.connect import ConnectionState, connect
from inngest.connect._internal.connection import WorkerConnection
from inngest.experimental import dev_server

from . import cases
from .cases.base import Case

_framework = server_lib.Framework.CONNECT
_env_var = const.EnvKey.CONNECT_ISOLATE_EXECUTION.value


# Need to create a client for each test class
def _create_client(suffix: str) -> inngest.Inngest:
    app_id = test_core.worker_suffix(f"{_framework.value}-functions-{suffix}")
    return inngest.Inngest(
        api_base_url=dev_server.server.origin,
        app_id=app_id,
        event_api_base_url=dev_server.server.origin,
        is_production=False,
    )


# Need to create a list of functions for each test class
def _create_fns(
    client: inngest.Inngest,
) -> tuple[list[Case], list[inngest.Function[typing.Any]]]:
    case_list = cases.create_async_cases(client, _framework)
    fns: list[inngest.Function[typing.Any]] = []
    for case in case_list:
        if isinstance(case.fn, list):
            fns.extend(case.fn)
        else:
            fns.append(case.fn)
    return case_list, fns


class _Base(unittest.IsolatedAsyncioTestCase):
    client: inngest.Inngest
    fns: list[inngest.Function[typing.Any]]
    conn: WorkerConnection
    conn_loop: asyncio.AbstractEventLoop
    conn_ready: threading.Event
    conn_thread: threading.Thread
    isolate_execution: bool

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        if cls.isolate_execution:
            os.environ[_env_var] = "1"
        else:
            os.environ[_env_var] = "0"

        cls.conn_ready = threading.Event()

        def run_connection() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            cls.conn_loop = loop

            async def start_conn() -> None:
                conn = connect([(cls.client, cls.fns)])
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
        os.environ.pop(_env_var, None)


_client_isolated = _create_client("isolated")
_cases_isolated, _fns_isolated = _create_fns(_client_isolated)


class TestFunctionsIsolated(_Base):
    client = _client_isolated
    fns = _fns_isolated
    isolate_execution = True


_client_non_isolated = _create_client("non-isolated")
_cases_non_isolated, _fns_non_isolated = _create_fns(_client_non_isolated)


class TestFunctionsNonIsolated(_Base):
    client = _client_non_isolated
    fns = _fns_non_isolated
    isolate_execution = False


for case in _cases_isolated:
    setattr(TestFunctionsIsolated, f"test_{case.name}", case.run_test)

for case in _cases_non_isolated:
    setattr(TestFunctionsNonIsolated, f"test_{case.name}", case.run_test)


if __name__ == "__main__":
    unittest.main()
