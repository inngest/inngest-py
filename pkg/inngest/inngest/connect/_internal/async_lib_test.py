from __future__ import annotations

import asyncio
import time
import unittest

import pytest

from .async_lib import run_sync


class TestRunSync(unittest.IsolatedAsyncioTestCase):
    async def test_with_running_loop(self) -> None:
        sleep_dur = 0.5
        result_holder: list[str] = []

        async def fn() -> str:
            await asyncio.sleep(sleep_dur)
            result_holder.append("completed")
            return "output"

        # Immediately returns
        with AssertDuration(0):
            future = run_sync(fn())

        assert not isinstance(future, Exception)

        # Returned immediately without blocking
        assert len(result_holder) == 0

        # Wait for the task to complete
        with AssertDuration(sleep_dur):
            output = await asyncio.wrap_future(future)
            assert output == "output"

        assert result_holder == ["completed"]

    async def test_with_exception(self) -> None:
        sleep_dur = 0.5

        async def fn() -> None:
            await asyncio.sleep(sleep_dur)
            raise ValueError("test error")

        future = run_sync(fn())
        assert not isinstance(future, Exception)

        with AssertDuration(sleep_dur):
            with pytest.raises(ValueError, match="test error"):
                await asyncio.wrap_future(future)

    async def test_multiple_tasks(self) -> None:
        sleep_dur = 0.5
        results: list[int] = []

        async def fn(value: int) -> None:
            await asyncio.sleep(sleep_dur)
            results.append(value)

        # Schedule multiple tasks
        future_1 = run_sync(fn(1))
        future_2 = run_sync(fn(2))
        future_3 = run_sync(fn(3))
        assert not isinstance(future_1, Exception)
        assert not isinstance(future_2, Exception)
        assert not isinstance(future_3, Exception)
        assert len(results) == 0

        with AssertDuration(sleep_dur):
            await asyncio.gather(
                asyncio.wrap_future(future_1),
                asyncio.wrap_future(future_2),
                asyncio.wrap_future(future_3),
            )

        # All tasks should have completed
        assert sorted(results) == [1, 2, 3]

    def test_no_event_loop(self) -> None:
        """
        Errors when no event loop is running. The missing event loop scenario is
        implicitly set up because the test method is not async
        """

        async def fn() -> None:
            pass

        result = run_sync(fn())

        assert isinstance(result, RuntimeError)


class AssertDuration:
    """
    Helper for asserting that a block of code takes a certain amount of time.
    This is a context manager, so use it in a `with` statement
    """

    def __init__(
        self,
        expected: float,
        *,
        tolerance: float = 0.2,
    ) -> None:
        """
        Args:
        ----
            expected: The expected duration in seconds.
            tolerance: The tolerance in seconds. This is only applied to the maximum duration.
        """

        self._expected = expected
        self._start_time: float = 0
        self._tolerance = tolerance

    def __enter__(self) -> AssertDuration:
        self._start_time = time.time()
        return self

    def __exit__(self, *args: object) -> None:
        elapsed = time.time() - self._start_time

        assert elapsed >= self._expected
        assert elapsed <= self._expected + self._tolerance


class TestAssertDuration:
    def test_assert_duration(self) -> None:
        with AssertDuration(0.1):
            time.sleep(0.1)

        with AssertDuration(0.1):
            time.sleep(0.2)

        with pytest.raises(AssertionError):
            with AssertDuration(0.1):
                time.sleep(0.05)
