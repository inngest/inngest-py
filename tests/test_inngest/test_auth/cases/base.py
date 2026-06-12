import dataclasses
import http
import json
import typing

import inngest
from inngest._internal import net, server_lib
from test_core import http_proxy

from .. import base

TestCase = base.TestCase
AuthResponse = base.AuthResponse
assert_sdk_handled_response = base.assert_sdk_handled_response
assert_unauthorized_response = base.assert_unauthorized_response
create_test_name = base.create_test_name

INVALID_SIGNATURE_HEADER = "t=0&s=invalid"
SIGNING_KEY = "signkey-prod-000000"
WRONG_SIGNING_KEY = "signkey-prod-111111"


@dataclasses.dataclass
class Case:
    name: str
    run_test: typing.Callable[[TestCase], None]


@dataclasses.dataclass
class MockCloud:
    proxy: http_proxy.Proxy
    request_bodies: list[bytes | None]


@dataclasses.dataclass
class ServedApp:
    fn_id: str


def serve_app(
    test_case: TestCase,
    framework: server_lib.Framework,
    *,
    is_production: bool,
    mock_cloud: MockCloud | None = None,
    name: str,
) -> ServedApp:
    client = inngest.Inngest(
        api_base_url=mock_cloud.proxy.origin
        if mock_cloud is not None
        else None,
        app_id=f"{framework.value}-{name}",
        is_production=is_production,
        signing_key=SIGNING_KEY if is_production else None,
    )

    @client.create_function(
        fn_id="foo",
        retries=0,
        trigger=inngest.TriggerEvent(event="app/foo"),
    )
    def fn(ctx: inngest.ContextSync) -> None:
        pass

    test_case.serve(
        client,
        [fn],
    )

    return ServedApp(fn_id=fn.id)


def execution_body() -> bytes:
    return json.dumps(
        {
            "ctx": {
                "attempt": 0,
                "disable_immediate_execution": False,
                "run_id": "run-id",
                "stack": {"stack": []},
            },
            "event": {"data": {}, "name": "app/foo"},
            "events": [{"data": {}, "name": "app/foo"}],
            "steps": {},
            "use_api": False,
        }
    ).encode("utf-8")


def in_band_sync_body() -> bytes:
    return json.dumps(
        server_lib.InBandSynchronizeRequest(
            url="http://test.local",
        ).to_dict()
    ).encode("utf-8")


def out_of_band_sync_body() -> bytes:
    return json.dumps({}).encode("utf-8")


def signed_headers(
    body: bytes, signing_key: str = SIGNING_KEY
) -> dict[str, str]:
    signature = net.sign_request(body, signing_key)
    if isinstance(signature, Exception):
        raise signature

    return {server_lib.HeaderKey.SIGNATURE.value: signature}


def in_band_headers(body: bytes, signing_key: str | None) -> dict[str, str]:
    headers = {
        server_lib.HeaderKey.SYNC_KIND.value: server_lib.SyncKind.IN_BAND.value,
    }
    if signing_key is not None:
        headers.update(signed_headers(body, signing_key))
    return headers


def run_get(
    test_case: TestCase,
    *,
    signing_key: str | None = None,
) -> AuthResponse:
    headers = signed_headers(b"", signing_key) if signing_key else {}
    return test_case.get(headers=headers)


def run_post(
    test_case: TestCase,
    *,
    body: bytes | None = None,
    fn_id: str,
    signing_key: str | None = None,
) -> AuthResponse:
    if body is None:
        body = execution_body()
    headers = signed_headers(body, signing_key) if signing_key else {}
    return test_case.post(
        body=body,
        headers=headers,
        path=f"/api/inngest?fnId={fn_id}",
    )


def run_in_band_put(
    test_case: TestCase,
    *,
    signing_key: str | None = None,
) -> AuthResponse:
    body = in_band_sync_body()
    return test_case.put(
        body=body,
        headers=in_band_headers(body, signing_key),
    )


def run_out_of_band_put(
    test_case: TestCase,
    *,
    signing_key: str | None = None,
) -> AuthResponse:
    body = out_of_band_sync_body()
    headers = signed_headers(body, signing_key) if signing_key else {}
    return test_case.put(body=body, headers=headers)


def run_patch(
    test_case: TestCase,
    *,
    signing_key: str | None = None,
) -> AuthResponse:
    body = b""
    headers = signed_headers(body, signing_key) if signing_key else {}
    return test_case.patch(body=body, headers=headers)


def assert_out_of_band_sync_succeeded(
    res: AuthResponse,
    mock_cloud: MockCloud,
) -> None:
    assert res.status_code == 200
    assert_sdk_handled_response(res)
    assert json.loads(res.body.decode("utf-8")) == {}
    assert len(mock_cloud.request_bodies) == 1
    assert mock_cloud.request_bodies[0] is not None


def assert_not_unauthorized(res: AuthResponse) -> None:
    assert_sdk_handled_response(res)
    assert json.loads(res.body.decode("utf-8")) != ({"message": "Unauthorized"})


def assert_unsupported_method_response(res: AuthResponse) -> None:
    headers = {key.lower(): value for key, value in res.headers.items()}
    inngest_headers = [key for key in headers if key.startswith("x-inngest-")]

    assert res.status_code in (
        http.HTTPStatus.NOT_FOUND,
        http.HTTPStatus.METHOD_NOT_ALLOWED,
    )
    assert headers.get(server_lib.HeaderKey.SERVER_TIMING.value) is None
    assert inngest_headers == []


def start_mock_cloud(
    test_case: TestCase,
) -> MockCloud:
    request_bodies: list[bytes | None] = []

    def on_request(
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> http_proxy.Response:
        request_bodies.append(body)
        return http_proxy.Response(
            body=json.dumps({}).encode("utf-8"),
            headers={},
            status_code=200,
        )

    proxy = http_proxy.Proxy(on_request).start()
    test_case.addCleanup(proxy.stop)
    return MockCloud(proxy=proxy, request_bodies=request_bodies)
