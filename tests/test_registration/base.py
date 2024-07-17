import dataclasses
import typing
import unittest

import inngest
from tests import base

create_test_name = base.create_test_name


@dataclasses.dataclass
class RegistrationResponse:
    body: bytes
    headers: dict[str, str]
    status_code: int


class TestCase(unittest.TestCase):
    def register(
        self,
        *,
        body: typing.Optional[bytes] = None,
        headers: typing.Optional[dict[str, str]] = None,
    ) -> RegistrationResponse:
        raise NotImplementedError()

    def serve(
        self,
        client: inngest.Inngest,
        fns: list[inngest.Function],
    ) -> None:
        raise NotImplementedError()
