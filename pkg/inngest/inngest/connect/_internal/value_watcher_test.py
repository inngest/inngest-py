import asyncio
import threading
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

    @pytest.mark.timeout(2, method="thread")
    async def test_immediate_false_waits_even_if_already_matching(self) -> None:
        """
        immediate=False should not return for a pre-existing match. It must
        wait for an actual transition.
        """

        watcher = ValueWatcher(1)

        wait_for_tasks = await self._start_tasks(
            watcher.wait_for(1, immediate=False),
        )

        # Value is already 1, but immediate=False means we're waiting for the
        # next transition to 1. Change away and back.
        watcher.value = 0
        watcher.value = 1

        await wait_for_tasks()

    @pytest.mark.timeout(2, method="thread")
    async def test_timeout_raises(self) -> None:
        watcher = ValueWatcher(0)

        with self.assertRaises(asyncio.TimeoutError):
            await watcher.wait_for(1, timeout=0.05)

    @pytest.mark.timeout(2, method="thread")
    async def test_wait_for_not_none(self) -> None:
        watcher = ValueWatcher[str | None](None)

        wait_for_tasks = await self._start_tasks(
            watcher.wait_for_not_none(),
        )

        watcher.value = "hello"

        await wait_for_tasks()

    @pytest.mark.timeout(2, method="thread")
    async def test_wait_for_not_none_immediate(self) -> None:
        watcher = ValueWatcher[str | None]("hello")

        result = await watcher.wait_for_not_none()
        self.assertEqual(result, "hello")

    @pytest.mark.timeout(2, method="thread")
    async def test_dedup_does_not_notify(self) -> None:
        """
        Setting the same value should not trigger a notification.
        """

        watcher = ValueWatcher(0)

        wait_for_tasks = await self._start_tasks(
            watcher.wait_for(1),
        )

        # Setting to the current value should be a no-op.
        watcher.value = 0
        watcher.value = 0

        # The watcher should still be waiting.
        await asyncio.sleep(0)
        self.assertFalse(
            all(
                t.done()
                for t in asyncio.all_tasks()
                if t is not asyncio.current_task()
            ),
        )

        # Now actually change it.
        watcher.value = 1
        await wait_for_tasks()

    @pytest.mark.timeout(2, method="thread")
    async def test_on_change_callback(self) -> None:
        changes: list[tuple[int, int]] = []

        watcher = ValueWatcher(
            0, on_change=lambda old, new: changes.append((old, new))
        )
        watcher.value = 1
        watcher.value = 2

        self.assertEqual(changes, [(0, 1), (1, 2)])

    @pytest.mark.timeout(2, method="thread")
    async def test_cross_thread_notification(self) -> None:
        """
        Value set from another thread should notify waiters.

        This test is important because different threads have different event
        loops. Some asyncio primitives are not thread-safe, so we need to make
        sure we aren't using them.
        """

        # Create a watcher in this thread
        watcher = ValueWatcher(0)

        # Create a waiter in this thread
        wait_for_tasks = await self._start_tasks(
            watcher.wait_for(1),
        )

        def other_thread() -> None:
            # Set the value in another thread
            watcher.value = 1

        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join()

        # Wait for the notification to come from the other thread
        await wait_for_tasks()
