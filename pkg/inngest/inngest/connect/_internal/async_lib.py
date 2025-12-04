from __future__ import annotations

import asyncio
import concurrent.futures
import typing

from inngest._internal import types


def run_sync(
    coro: typing.Coroutine[typing.Any, typing.Any, types.T],
) -> types.MaybeError[concurrent.futures.Future[types.T]]:
    """
    Schedule an async coroutine to run in the event loop from a sync context.
    This is useful when you need to call async code from a sync function.
    """

    try:
        loop = asyncio.get_running_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop)
    except RuntimeError as e:
        return e
