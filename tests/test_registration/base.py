import dataclasses
import unittest

import inngest
from tests import base

create_test_name = base.create_test_name


@dataclasses.dataclass
class RegistrationResponse:
    body: object
    status_code: int


class TestCase(unittest.TestCase):
    def register(self, headers: dict[str, str]) -> RegistrationResponse:
        raise NotImplementedError()

    def serve(
        self,
        client: inngest.Inngest,
        fns: list[inngest.Function],
    ) -> None:
        raise NotImplementedError()
