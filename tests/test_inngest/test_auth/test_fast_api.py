import json
import typing
import unittest

import fastapi
import fastapi.testclient
import inngest
import inngest.fast_api
from inngest._internal import server_lib

from . import base, cases

_framework = server_lib.Framework.FAST_API


class TestAuth(base.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.app = fastapi.FastAPI()
        self.app_client = fastapi.testclient.TestClient(self.app)

    def get(
        self,
        *,
        headers: dict[str, str] | None = None,
    ) -> base.AuthResponse:
        if headers is None:
            headers = {}

        res = self.app_client.get(
            "/api/inngest",
            headers=headers,
        )
        return base.AuthResponse(
            body=res.content,
            headers=dict(res.headers),
            status_code=res.status_code,
        )

    def post(
        self,
        *,
        body: bytes,
        headers: dict[str, str] | None = None,
        path: str = "/api/inngest",
    ) -> base.AuthResponse:
        if headers is None:
            headers = {}

        res = self.app_client.post(
            path,
            content=body,
            headers=headers,
        )
        return base.AuthResponse(
            body=res.content,
            headers=dict(res.headers),
            status_code=res.status_code,
        )

    def put(
        self,
        *,
        body: dict[str, object] | bytes,
        headers: dict[str, str] | None = None,
    ) -> base.AuthResponse:
        if isinstance(body, bytes):
            body = json.loads(body)

        if headers is None:
            headers = {}

        res = self.app_client.put(
            "/api/inngest",
            json=body,
            headers=headers,
        )
        return base.AuthResponse(
            body=res.content,
            headers=dict(res.headers),
            status_code=res.status_code,
        )

    def patch(
        self,
        *,
        body: bytes,
        headers: dict[str, str] | None = None,
    ) -> base.AuthResponse:
        if headers is None:
            headers = {}

        res = self.app_client.patch(
            "/api/inngest",
            content=body,
            headers=headers,
        )
        return base.AuthResponse(
            body=res.content,
            headers=dict(res.headers),
            status_code=res.status_code,
        )

    def serve(
        self,
        client: inngest.Inngest,
        fns: list[inngest.Function[typing.Any]],
    ) -> None:
        inngest.fast_api.serve(
            self.app,
            client,
            fns,
        )


for case in cases.create_cases(_framework):
    test_name = f"test_{case.name}"
    setattr(TestAuth, test_name, case.run_test)


if __name__ == "__main__":
    unittest.main()
