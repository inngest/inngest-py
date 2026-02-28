from __future__ import annotations

import asyncio
import typing

T = typing.TypeVar("T")
S = typing.TypeVar("S")


class ValueWatcher(typing.Generic[T]):
    """
    A container that allows consumers to reactively wait for value changes.

    This pattern enables clean coordination between handlers without tight
    coupling or polling.
    """

    _on_changes: list[typing.Callable[[T, T], None]]

    def __init__(
        self,
        initial_value: T,
        *,
        on_change: typing.Callable[[T, T], None] | None = None,
    ) -> None:
        """
        Args:
            initial_value: The initial value.
            on_change: Called when the value changes. Good for debug logging.
        """

        self._on_changes = []
        if on_change:
            self._on_changes.append(on_change)

        # Every watcher gets its own queue. The queue is used to communicate
        # value changes, so its items are tuples of the old and new values.
        self._watch_queues: list[asyncio.Queue[tuple[T, T]]] = []

        # Hold references to fire-and-forget tasks to prevent GC.
        self._background_tasks: set[asyncio.Task[T]] = set()

        self._value = initial_value

    @property
    def value(self) -> T:
        return self._value

    @value.setter
    def value(self, new_value: T) -> None:
        if new_value == self._value:
            return

        old_value = self._value
        self._value = new_value

        # Notify all watchers.
        for queue in self._watch_queues:
            queue.put_nowait((old_value, new_value))

        for on_change in self._on_changes:
            on_change(old_value, new_value)

    def on_change(self, on_change: typing.Callable[[T, T], None]) -> None:
        """
        Add a callback that's called when the value changes.

        Args:
            on_change: The callback to call when the value changes.
        """

        self._on_changes.append(on_change)

    def on_value(self, value: T, cb: typing.Callable[[], None]) -> None:
        """
        Add a callback that's called when the value is equal to the given value.
        Will not call the callback more than once.
        """

        task = asyncio.create_task(self.wait_for(value))
        self._background_tasks.add(task)

        def _done(t: asyncio.Task[T]) -> None:
            self._background_tasks.discard(t)
            if not t.cancelled() and t.exception() is None:
                cb()

        task.add_done_callback(_done)

    async def wait_for(
        self,
        value: T,
        *,
        immediate: bool = True,
        timeout: float | None = None,
    ) -> T:
        """
        Wait for the value to be equal to the given value.

        Args:
            value: Return when the value is equal to this.
            immediate: If True and the value is already equal to the given value, return immediately. Defaults to True.
            timeout: Seconds to wait before raising asyncio.TimeoutError. None means wait forever.
        """

        return await self._wait_for_condition(
            lambda v: v == value,
            immediate=immediate,
            timeout=timeout,
        )

    async def wait_for_not(
        self,
        value: T,
        *,
        immediate: bool = True,
        timeout: float | None = None,
    ) -> T:
        """
        Wait for the value to not be equal to the given value.

        Args:
            value: Return when the value is not equal to this.
            immediate: If True and the value is already not equal to the given value, return immediately. Defaults to True.
            timeout: Seconds to wait before raising asyncio.TimeoutError. None means wait forever.
        """

        return await self._wait_for_condition(
            lambda v: v != value,
            immediate=immediate,
            timeout=timeout,
        )

    async def wait_for_not_none(
        self: ValueWatcher[S | None],
        *,
        immediate: bool = True,
        timeout: float | None = None,
    ) -> S:
        """
        Wait for the value to be not None.

        Args:
            immediate: If True and the value is already not None, return immediately. Defaults to True.
            timeout: Seconds to wait before raising asyncio.TimeoutError. None means wait forever.
        """

        result = await self._wait_for_condition(
            lambda v: v is not None,
            immediate=immediate,
            timeout=timeout,
        )
        if result is None:
            raise AssertionError("unreachable")
        return result

    async def _wait_for_condition(
        self,
        condition: typing.Callable[[T], bool],
        *,
        immediate: bool = True,
        timeout: float | None = None,
    ) -> T:
        """
        Internal method to DRY race condition handling in other methods.
        """

        # Fast path: no task needed if the value already matches.
        if immediate and condition(self._value):
            return self._value

        async def _wait() -> T:
            with self._watch() as watch:
                # Re-check after queue registration to close the gap
                # between the fast path above and the queue being live.
                if immediate and condition(self._value):
                    return self._value

                async for _, new in watch:
                    if condition(new):
                        return new

            raise AssertionError("unreachable")

        return await asyncio.wait_for(_wait(), timeout=timeout)

    async def wait_for_change(
        self,
        *,
        timeout: float | None = None,
    ) -> T:
        """
        Wait for the value to change.

        Args:
            timeout: Seconds to wait before raising asyncio.TimeoutError. None means wait forever.
        """

        async def _wait() -> T:
            with self._watch() as watch:
                async for _, new in watch:
                    return new

            raise AssertionError("unreachable")

        return await asyncio.wait_for(_wait(), timeout=timeout)

    def _watch(self) -> _WatchContextManager[T]:
        """
        Watch for all changes to the value. This method returns a context
        manager so it must be used in a `with` statement.

        Its return value is an async generator that yields tuples of the old and
        new values.
        """

        queue = asyncio.Queue[tuple[T, T]]()
        self._watch_queues.append(queue)

        return _WatchContextManager(
            on_exit=lambda: self._watch_queues.remove(queue),
            queue=queue,
        )


class _WatchContextManager(typing.Generic[T]):
    """
    Context manager that's used to automatically delete a queue when it's no
    longer being watched.

    Its return value is an async generator that yields tuples of the old and
    new values.
    """

    def __init__(
        self,
        on_exit: typing.Callable[[], None],
        queue: asyncio.Queue[tuple[T, T]],
    ) -> None:
        self._on_exit = on_exit
        self._queue = queue

    def __enter__(self) -> typing.AsyncGenerator[tuple[T, T], None]:
        async def _watch() -> typing.AsyncGenerator[tuple[T, T], None]:
            while True:
                yield await self._queue.get()

        return _watch()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self._on_exit()
