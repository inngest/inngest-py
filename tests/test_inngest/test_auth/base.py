import dataclasses
import http
import json
import typing
import unittest

import inngest
from inngest._internal import server_lib
from test_core import base

create_test_name = base.create_test_name


@dataclasses.dataclass
class AuthResponse:
    body: bytes
    headers: dict[str, str]
    status_code: int


class TestCase(unittest.TestCase):
    def get(
        self,
        *,
        headers: dict[str, str] | None = None,
    ) -> AuthResponse:
        raise NotImplementedError()

    def post(
        self,
        *,
        body: bytes,
        headers: dict[str, str] | None = None,
        path: str = "/api/inngest",
    ) -> AuthResponse:
        raise NotImplementedError()

    def put(
        self,
        *,
        body: dict[str, object] | bytes,
        headers: dict[str, str] | None = None,
    ) -> AuthResponse:
        raise NotImplementedError()

    def patch(
        self,
        *,
        body: bytes,
        headers: dict[str, str] | None = None,
    ) -> AuthResponse:
        raise NotImplementedError()

    def serve(
        self,
        client: inngest.Inngest,
        fns: list[inngest.Function[typing.Any]],
    ) -> None:
        raise NotImplementedError()


def assert_unauthorized_response(res: AuthResponse) -> None:
    headers = {key.lower(): value for key, value in res.headers.items()}
    inngest_headers = [
        key
        for key in headers
        if key.startswith("x-inngest-")
        and key != server_lib.HeaderKey.SDK_HANDLED.value
    ]

    assert res.status_code == http.HTTPStatus.UNAUTHORIZED
    assert json.loads(res.body.decode("utf-8")) == {"message": "Unauthorized"}
    assert headers.get(server_lib.HeaderKey.SDK_HANDLED.value) == "true"
    assert headers.get(server_lib.HeaderKey.SERVER_TIMING.value) is not None
    assert headers.get(server_lib.HeaderKey.SIGNATURE.value) is None
    assert inngest_headers == []


def assert_sdk_handled_response(res: AuthResponse) -> None:
    headers = {key.lower(): value for key, value in res.headers.items()}

    assert headers.get(server_lib.HeaderKey.SDK_HANDLED.value) == "true"
