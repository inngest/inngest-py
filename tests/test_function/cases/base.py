import dataclasses
import os
import typing

import inngest
from inngest._internal import const
from tests import base

BaseState = base.BaseState
wait_for = base.wait_for


class TestClass(typing.Protocol):
    client: inngest.Inngest


@dataclasses.dataclass
class Case:
    fn: typing.Union[inngest.Function, list[inngest.Function]]
    name: str
    run_test: typing.Callable[[TestClass], None]


def create_event_name(framework: const.Framework, test_name: str) -> str:
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


def create_test_name(
    test_name: str,
    is_sync: bool,
) -> str:
    if is_sync:
        test_name += "_sync"
    return test_name
