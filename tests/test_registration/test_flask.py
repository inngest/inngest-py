import os
import typing
import unittest

import flask
import flask.logging
import flask.testing

import inngest
import inngest.flask
from inngest._internal import const, server_lib

from . import base, cases

_framework = server_lib.Framework.FLASK


class TestRegistration(base.TestCase):
    def setUp(self) -> None:
        super().setUp()

        # TODO: Delete this when we default to allowing in-band sync
        os.environ[const.EnvKey.ALLOW_IN_BAND_SYNC.value] = "1"

        self.app = flask.Flask(__name__)
        self.app_client = self.app.test_client()

    def tearDown(self) -> None:
        super().tearDown()

        # TODO: Delete this when we default to allowing in-band sync
        os.environ.pop(const.EnvKey.ALLOW_IN_BAND_SYNC.value, None)

    def put(
        self,
        *,
        body: typing.Union[dict[str, object], bytes],
        headers: typing.Optional[dict[str, str]] = None,
    ) -> base.RegistrationResponse:
        if headers is None:
            headers = {}

        res = self.app_client.put(
            "/api/inngest",
            data=body,
            headers=headers,
        )
        return base.RegistrationResponse(
            body=res.data,
            headers=dict(res.headers.items()),
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
