import dataclasses
import typing

from .. import base

TestCase = base.TestCase


@dataclasses.dataclass
class Case:
    name: str
    run_test: typing.Callable[[TestCase], None]


create_test_name = base.create_test_name
