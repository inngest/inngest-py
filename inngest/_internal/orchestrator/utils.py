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
