import asyncio
import dataclasses
import unittest

import pytest

from .models import _ValueWatcher


class TestValueWatcher(unittest.IsolatedAsyncioTestCase):
    @pytest.mark.timeout(3)
    async def test_watch_fanout(self) -> None:
        watcher = _ValueWatcher(0)

        @dataclasses.dataclass
        class State:
            watch_1_values: list[int]
            watch_2_values: list[int]

        state = State(watch_1_values=[], watch_2_values=[])

        async def watch_fast() -> None:
            async for value in watcher.watch():
                state.watch_1_values.append(value)
                if value == 2:
                    break

        async def watch_slow() -> None:
            async for value in watcher.watch():
                # Make this watch slightly slower to test for races.
                await asyncio.sleep(0.1)

                state.watch_2_values.append(value)
                if value == 2:
                    break

        tasks = [
            asyncio.create_task(watch_fast()),
            asyncio.create_task(watch_slow()),
        ]
        for task in tasks:
            self.addCleanup(task.cancel)

        # Allow an event loop iteration to pass, ensuring that our watch tasks
        # start before we set the value.
        await asyncio.sleep(0)

        # Set the value, which should propagate to all watchers.
        watcher.value = 1

        # Wait long enough for the slow watch.
        await asyncio.sleep(0.2)

        # Set the value again, which should propagate to all watchers.
        watcher.value = 2

        # Wait for all watchers to complete.
        await asyncio.gather(*tasks)
        self.assertEqual(state.watch_1_values, [1, 2])
        self.assertEqual(state.watch_2_values, [1, 2])
