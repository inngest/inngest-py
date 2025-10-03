import asyncio
import inspect

import typing_extensions

from .. import execution_lib, types


def is_function_handler_async(
    value: execution_lib.FunctionHandlerAsync[types.T]
    | execution_lib.FunctionHandlerSync[types.T],
) -> typing_extensions.TypeGuard[execution_lib.FunctionHandlerAsync[types.T]]:
    return inspect.iscoroutinefunction(value)


def is_function_handler_sync(
    value: execution_lib.FunctionHandlerAsync[types.T]
    | execution_lib.FunctionHandlerSync[types.T],
) -> typing_extensions.TypeGuard[execution_lib.FunctionHandlerSync[types.T]]:
    return not inspect.iscoroutinefunction(value)


async def wait_for_next_loop() -> None:
    loop = asyncio.get_event_loop()
    fut = asyncio.Future[None]()
    loop.call_soon(lambda: fut.set_result(None))
    await fut
