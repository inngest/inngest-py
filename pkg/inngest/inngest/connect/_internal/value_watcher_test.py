import asyncio
import typing
import unittest

import pytest

from .value_watcher import ValueWatcher


class TestValueWatcher(unittest.IsolatedAsyncioTestCase):
    async def _start_tasks(
        self, *coros: typing.Coroutine[typing.Any, typing.Any, typing.Any]
    ) -> typing.Callable[[], typing.Awaitable[None]]:
        tasks = [asyncio.create_task(coro) for coro in coros]
        for task in tasks:
            self.addCleanup(task.cancel)

        # Allow an event loop iteration to pass, ensuring that the tasks start.
        await asyncio.sleep(0)

        async def wait() -> None:
            await asyncio.gather(*tasks)

        return wait

    @pytest.mark.timeout(2, method="thread")
    async def test_wait_for(self) -> None:
        watcher = ValueWatcher(0)

        # Immediately returns because the value is already 0.
        await watcher.wait_for(0)

        wait_for_tasks = await self._start_tasks(
            watcher.wait_for(1),
        )

        watcher.value = 1

        # Wait for all watchers to complete.
        await wait_for_tasks()

    @pytest.mark.timeout(2, method="thread")
    async def test_wait_for_not(self) -> None:
        watcher = ValueWatcher(0)

        # Immediately returns because the value is already 0.
        await watcher.wait_for_not(1)

        wait_for_tasks = await self._start_tasks(
            watcher.wait_for_not(0),
        )

        watcher.value = 1

        # Wait for all watchers to complete.
        await wait_for_tasks()

    @pytest.mark.timeout(2, method="thread")
    async def test_wait_for_change(self) -> None:
        watcher = ValueWatcher(0)

        wait_for_tasks = await self._start_tasks(
            watcher.wait_for_change(),
        )

        watcher.value = 1

        # Wait for all watchers to complete.
        await wait_for_tasks()

    @pytest.mark.timeout(2, method="thread")
    async def test_watch_wait_for_and_not(self) -> None:
        """
        Match parallel watchers:
        - Wait for the value to not be a certain value.
        - Wait for the value to be a certain value.
        """

        watcher = ValueWatcher(0)

        wait_for_tasks = await self._start_tasks(
            watcher.wait_for_not(0),
            watcher.wait_for(1),
        )

        # Set the value, which should propagate to all watchers.
        watcher.value = 1

        # Wait for all watchers to complete.
        await wait_for_tasks()

    @pytest.mark.timeout(2, method="thread")
    async def test_quickly_set_twice(self) -> None:
        """
        Setting twice really quickly should not cause a missed value.
        """

        watcher = ValueWatcher(0)

        wait_for_tasks = await self._start_tasks(
            watcher.wait_for(1),
            watcher.wait_for(2),
        )

        # Set the value, which should propagate to all watchers.
        watcher.value = 1
        watcher.value = 2

        # Wait for all watchers to complete.
        await wait_for_tasks()
