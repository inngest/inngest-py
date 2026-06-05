import typing
import unittest

import flask
import inngest
import inngest.flask
from inngest._internal import server_lib

from . import base, cases

_framework = server_lib.Framework.FLASK


class TestAuth(base.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.app = flask.Flask(__name__)
        self.app_client = self.app.test_client()

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
            body=res.data,
            headers=dict(res.headers.items()),
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
            data=body,
            headers=headers,
        )
        return base.AuthResponse(
            body=res.data,
            headers=dict(res.headers.items()),
            status_code=res.status_code,
        )

    def put(
        self,
        *,
        body: dict[str, object] | bytes,
        headers: dict[str, str] | None = None,
    ) -> base.AuthResponse:
        if headers is None:
            headers = {}

        res = self.app_client.put(
            "/api/inngest",
            data=body,
            headers=headers,
        )
        return base.AuthResponse(
            body=res.data,
            headers=dict(res.headers.items()),
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
            data=body,
            headers=headers,
        )
        return base.AuthResponse(
            body=res.data,
            headers=dict(res.headers.items()),
            status_code=res.status_code,
        )

    def serve(
        self,
        client: inngest.Inngest,
        fns: list[inngest.Function[typing.Any]],
        *,
        enable_unauthed_sync: bool | None = None,
    ) -> None:
        inngest.flask.serve(
            self.app,
            client,
            fns,
            enable_unauthed_sync=enable_unauthed_sync,
        )


for case in cases.create_cases(_framework):
    test_name = f"test_{case.name}"
    setattr(TestAuth, test_name, case.run_test)

if __name__ == "__main__":
    unittest.main()
