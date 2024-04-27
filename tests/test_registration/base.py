import dataclasses
import unittest

import inngest


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
