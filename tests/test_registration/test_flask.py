import unittest

import flask
import flask.logging
import flask.testing

import inngest
import inngest.flask
from inngest._internal import const

from . import base, cases

_framework = const.Framework.FLASK


class TestRegistration(base.TestCase):
    def setUp(self) -> None:
        self.app = flask.Flask(__name__)
        self.app_client = self.app.test_client()

    def register(self, headers: dict[str, str]) -> base.RegistrationResponse:
        res = self.app_client.put(
            "/api/inngest",
            headers=headers,
        )
        return base.RegistrationResponse(
            body=res.json,
            status_code=res.status_code,
        )

    def serve(
        self,
        client: inngest.Inngest,
        fns: list[inngest.Function],
    ) -> None:
        inngest.flask.serve(
            self.app,
            client,
            fns,
        )


for case in cases.create_cases(_framework):
    test_name = f"test_{case.name}"
    setattr(TestRegistration, test_name, case.run_test)

if __name__ == "__main__":
    unittest.main()
