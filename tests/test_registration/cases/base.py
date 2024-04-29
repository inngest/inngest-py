import dataclasses
import typing

from .. import base

TestCase = base.TestCase


@dataclasses.dataclass
class Case:
    name: str
    run_test: typing.Callable[[TestCase], None]
