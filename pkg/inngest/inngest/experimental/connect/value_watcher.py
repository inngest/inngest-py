from __future__ import annotations

import asyncio
import typing

T = typing.TypeVar("T")


class _ValueWatcher(typing.Generic[T]):
    """
    A container that allows consumers to watch for changes to the wrapped value.
    """

    def __init__(
        self,
        initial_value: T,
        *,
        on_change: typing.Optional[typing.Callable[[T, T], None]] = None,
    ) -> None:
        """
        Args:
            initial_value: The initial value.
            on_change: Called when the value changes. Good for debug logging.
        """

        self._on_change = on_change

        # Every watcher gets its own queue. The queue is used to communicate
        # value changes, so its items are tuples of the old and new values.
        self._watch_queues: list[asyncio.Queue[tuple[T, T]]] = []

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

        if self._on_change:
            self._on_change(old_value, new_value)

    async def wait_for(self, value: T) -> None:
        """
        Wait for the value to be equal to the given value.
        """

        if self._value == value:
            # No need to wait.
            return

        with self._watch() as watch:
            async for _, new in watch:
                if new == value:
                    return

    async def wait_for_not(self, value: T) -> None:
        """
        Wait for the value to not be equal to the given value.
        """

        if self._value != value:
            # No need to wait.
            return

        with self._watch() as watch:
            async for _, new in watch:
                if new != value:
                    return

    async def wait_for_change(self) -> None:
        """
        Wait for the value to change.
        """

        with self._watch() as watch:
            async for _ in watch:
                return

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
        exc_type: typing.Optional[type[BaseException]],
        exc_value: typing.Optional[BaseException],
        traceback: object,
    ) -> None:
        self._on_exit()
