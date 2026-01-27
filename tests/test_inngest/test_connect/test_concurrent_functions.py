import asyncio
import concurrent.futures
import time

import inngest
import test_core
from inngest.connect import ConnectionState, connect
from inngest.experimental import ThreadPoolConfig

from .base import BaseTest


class TestConcurrentAsyncFunctions(BaseTest):
    async def test(self) -> None:
        """
        Test that async functions can be run concurrently. Under-the-hood, this
        is accomplished with a ThreadPoolExecutor that is shared across all
        functions.
        """

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )
        event_name = test_core.random_suffix("event")
        run_ids = set[str]()

        @client.create_function(
            fn_id="fn",
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.ContextSync) -> None:
            run_ids.add(ctx.run_id)

            # This will loop forever if the function run is blocking the event
            # loop, causing the test to timeout.
            while True:
                if len(run_ids) == 2:
                    break
                time.sleep(0.1)  # noqa: ASYNC251

        conn = connect(
            [(client, [fn])],
            _experimental_thread_pool=ThreadPoolConfig(
                enable_for_async_fns=True,
                pool=concurrent.futures.ThreadPoolExecutor(),
            ),
        )
        task = asyncio.create_task(conn.start())
        self.addCleanup(conn.close, wait=True)
        self.addCleanup(task.cancel)
        await conn.wait_for_state(ConnectionState.ACTIVE)

        # Trigger the function and wait for it to complete.
        await client.send(
            [
                inngest.Event(name=event_name),
                inngest.Event(name=event_name),
            ]
        )

        def assert_runs() -> None:
            assert len(run_ids) == 2

        await test_core.wait_for(assert_runs)

        i = iter(run_ids)
        run_1_id = next(i)
        run_2_id = next(i)

        await test_core.helper.client.wait_for_run_status(
            run_1_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        await test_core.helper.client.wait_for_run_status(
            run_2_id,
            test_core.helper.RunStatus.COMPLETED,
        )


class TestConcurrentSyncFunctions(BaseTest):
    async def test(self) -> None:
        """
        Test that sync functions can be run concurrently. Under-the-hood, this
        is accomplished with a ThreadPoolExecutor that is shared across all
        functions.
        """

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )
        event_name = test_core.random_suffix("event")
        run_ids = set[str]()

        @client.create_function(
            fn_id="fn",
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        def fn(ctx: inngest.ContextSync) -> None:
            run_ids.add(ctx.run_id)

            # This will loop forever if the function run is blocking the event
            # loop, causing the test to timeout.
            while True:
                if len(run_ids) == 2:
                    break
                time.sleep(0.1)

        conn = connect([(client, [fn])])
        task = asyncio.create_task(conn.start())
        self.addCleanup(conn.close, wait=True)
        self.addCleanup(task.cancel)
        await conn.wait_for_state(ConnectionState.ACTIVE)

        # Trigger the function and wait for it to complete.
        await client.send(
            [
                inngest.Event(name=event_name),
                inngest.Event(name=event_name),
            ]
        )

        def assert_runs() -> None:
            assert len(run_ids) == 2

        await test_core.wait_for(assert_runs)

        i = iter(run_ids)
        run_1_id = next(i)
        run_2_id = next(i)

        await test_core.helper.client.wait_for_run_status(
            run_1_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        await test_core.helper.client.wait_for_run_status(
            run_2_id,
            test_core.helper.RunStatus.COMPLETED,
        )
