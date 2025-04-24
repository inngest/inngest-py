import asyncio
import time
import unittest

from . import async_lib


class TestThreadPool(unittest.IsolatedAsyncioTestCase):
    async def test_exceed_max_workers(self) -> None:
        pool = async_lib.ThreadPool(1)

        counter = 0

        async def increment() -> None:
            nonlocal counter

            while True:
                await asyncio.sleep(0.1)
                counter += 1

        task = asyncio.create_task(increment())
        self.addCleanup(task.cancel)

        def block() -> None:
            time.sleep(2)

        start = time.time()
        await pool.run_in_thread(block)
        await pool.run_in_thread(block)

        # Sync functions run sequentially.
        assert round(time.time() - start, 1) == 4

        # Assert that the increment function was called every 0.1 seconds. We'll
        # do that by checking that the counter was incremented roughly 10 times
        # per second.
        assert counter >= 39
        assert counter <= 41
