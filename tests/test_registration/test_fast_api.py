import json
import typing
import unittest

import fastapi
import fastapi.testclient

import inngest
import inngest.fast_api
from inngest._internal import net, server_lib

from . import base, cases

_framework = server_lib.Framework.FAST_API


class TestRegistration(base.TestCase):
    def setUp(self) -> None:
        self.app = fastapi.FastAPI()
        self.app_client = fastapi.testclient.TestClient(self.app)

    def register(
        self,
        *,
        body: typing.Optional[bytes] = None,
        headers: typing.Optional[dict[str, str]] = None,
    ) -> base.RegistrationResponse:
        data = None
        if isinstance(body, bytes):
            data = json.loads(body.decode("utf-8"))

        res = self.app_client.put(
            "/api/inngest",
            headers=headers,
            json=data,
        )

        return base.RegistrationResponse(
            body=res.read(),
            headers=net.normalize_headers(
                {k: v for k, v in res.headers.items()}
            ),
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
