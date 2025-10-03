import dataclasses
import os
import typing

import inngest
from inngest._internal import server_lib
from test_core import base

BaseState = base.BaseState
create_test_name = base.create_test_name
wait_for = base.wait_for


class TestClass(typing.Protocol):
    client: inngest.Inngest

    def addCleanup(
        self,
        function: typing.Callable[..., typing.Any],
        /,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None: ...


@dataclasses.dataclass
class Case:
    fn: inngest.Function[typing.Any] | list[inngest.Function[typing.Any]]
    name: str
    run_test: typing.Callable[[TestClass], typing.Awaitable[None]]


def create_event_name(framework: server_lib.Framework, test_name: str) -> str:
    suffix = ""
    worker_id = os.getenv("PYTEST_XDIST_WORKER")
    if worker_id:
        suffix += f"-{worker_id}"

    return f"{framework.value}/{test_name}{suffix}"


def create_fn_id(test_name: str) -> str:
    suffix = ""
    worker_id = os.getenv("PYTEST_XDIST_WORKER")
    if worker_id:
        suffix += f"-{worker_id}"

    return test_name + suffix


P = typing.ParamSpec("P")
T = typing.TypeVar("T")


def asyncify(
    fn: typing.Callable[P, T],
) -> typing.Callable[P, typing.Awaitable[T]]:
    """
    Convert a sync function to an async function.
    """

    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        return fn(*args, **kwargs)

    return wrapper
