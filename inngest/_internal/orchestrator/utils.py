import asyncio
import inspect
import typing

import typing_extensions

from ..execution.models import FunctionHandlerAsync, FunctionHandlerSync


def is_function_handler_async(
    value: typing.Union[FunctionHandlerAsync, FunctionHandlerSync],
) -> typing_extensions.TypeGuard[FunctionHandlerAsync]:
    return inspect.iscoroutinefunction(value)


def is_function_handler_sync(
    value: typing.Union[FunctionHandlerAsync, FunctionHandlerSync],
) -> typing_extensions.TypeGuard[FunctionHandlerSync]:
    return not inspect.iscoroutinefunction(value)


async def wait_for_next_loop() -> None:
    loop = asyncio.get_event_loop()
    fut = asyncio.Future[None]()
    loop.call_soon(lambda: fut.set_result(None))
    await fut


async def wait_forever() -> None:
    while True:
        await asyncio.sleep(60)
