import json
import os
import typing
import unittest

import fastapi
import fastapi.testclient

import inngest
import inngest.fast_api
from inngest._internal import const, server_lib

from . import base, cases

_framework = server_lib.Framework.FAST_API


class TestRegistration(base.TestCase):
    def setUp(self) -> None:
        super().setUp()

        # TODO: Delete this when we default to allowing in-band sync
        os.environ[const.EnvKey.ALLOW_IN_BAND_SYNC.value] = "1"

        self.app = fastapi.FastAPI()
        self.app_client = fastapi.testclient.TestClient(self.app)

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
        if isinstance(body, bytes):
            body = json.loads(body)

        if headers is None:
            headers = {}

        res = self.app_client.put(
            "/api/inngest",
            json=body,
            headers=headers,
        )
        return base.RegistrationResponse(
            body=res.content,
            headers=dict(res.headers),
            status_code=res.status_code,
        )

    def serve(
        self,
        client: inngest.Inngest,
        fns: list[inngest.Function],
    ) -> None:
        inngest.fast_api.serve(
            self.app,
            client,
            fns,
        )


for case in cases.create_cases(_framework):
    test_name = f"test_{case.name}"
    setattr(TestRegistration, test_name, case.run_test)


if __name__ == "__main__":
    unittest.main()
