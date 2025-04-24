from __future__ import annotations

import asyncio
import concurrent.futures
import typing

from inngest._internal import types


def get_event_loop() -> typing.Optional[asyncio.AbstractEventLoop]:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return None

    return loop


async def run_in_thread(
    executor: concurrent.futures.Executor,
    func: typing.Callable[..., types.T],
) -> types.T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, func)


class _CountingSemaphore:
    def __init__(self, initial_value: int = 1) -> None:
        self.counter: int = initial_value
        self.waiters: list[asyncio.Future[bool]] = []

    async def acquire(self) -> bool:
        if self.counter > 0:
            self.counter -= 1
            return True

        # No resources available, create a future and wait
        future: asyncio.Future[bool] = asyncio.Future()
        self.waiters.append(future)
        await future
        return True

    def release(self) -> None:
        self.counter += 1

        # If there are waiters, wake one up.
        if self.waiters and self.counter > 0:
            waiter: asyncio.Future[bool] = self.waiters.pop(0)
            if not waiter.done():
                self.counter -= 1
                waiter.set_result(True)

    async def __aenter__(self) -> _CountingSemaphore:
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: typing.Optional[type],
        exc_val: typing.Optional[Exception],
        exc_tb: typing.Optional[object],
    ) -> None:
        self.release()


class ThreadPool:
    """
    A thread pool that runs non-async functions in a non-blocking way. It's a
    thin wrapper around ThreadPoolExecutor, including a counting semaphore to
    keep the number of threads below the max workers. Without this protection,
    exceeding max workers blocks the thread.
    """

    _loop: typing.Optional[asyncio.AbstractEventLoop] = None

    @property
    def max_workers(self) -> int:
        return self._executor._max_workers

    def __init__(self, max_workers: typing.Optional[int]) -> None:
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers
        )
        self._semaphore = _CountingSemaphore(self._executor._max_workers)

    async def run_in_thread(
        self,
        func: typing.Callable[[], types.T],
    ) -> types.T:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        async with self._semaphore:
            return await self._loop.run_in_executor(self._executor, func)
