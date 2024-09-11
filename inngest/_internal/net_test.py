import hashlib
import hmac
import json
import os
import time
import typing
import unittest
import unittest.mock

import httpx

from inngest._internal import const, errors, net, server_lib, transforms, types

_signing_key = "signkey-prod-000000"
_signing_key_fallback = "signkey-prod-111111"


class Test_create_serve_url(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        os.environ.pop(const.EnvKey.SERVE_ORIGIN.value, None)
        os.environ.pop(const.EnvKey.SERVE_PATH.value, None)

    def test_only_request_url(self) -> None:
        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin=None,
            serve_path=None,
        )
        expected = "https://foo.test/api/inngest"
        assert actual == expected

    def test_serve_origin(self) -> None:
        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin="https://bar.test",
            serve_path=None,
        )
        expected = "https://bar.test/api/inngest"
        assert actual == expected

    def test_serve_origin_env_var(self) -> None:
        os.environ[const.EnvKey.SERVE_ORIGIN.value] = "https://bar-env.test"

        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin="https://bar.test",
            serve_path=None,
        )
        expected = "https://bar-env.test/api/inngest"
        assert actual == expected

    def test_serve_origin_missing_scheme(self) -> None:
        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin="bar.test",
            serve_path=None,
        )
        expected = "https://bar.test/api/inngest"
        assert actual == expected

    def test_serve_origin_port(self) -> None:
        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin="https://bar.test:8080",
            serve_path=None,
        )
        expected = "https://bar.test:8080/api/inngest"
        assert actual == expected

    def test_serve_path(self) -> None:
        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin=None,
            serve_path="/custom/path",
        )
        expected = "https://foo.test/custom/path"
        assert actual == expected

    def test_serve_path_env_var(self) -> None:
        os.environ[const.EnvKey.SERVE_PATH.value] = "/env/path"

        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin=None,
            serve_path="/custom/path",
        )
        expected = "https://foo.test/env/path"
        assert actual == expected

    def test_serve_origin_and_path(self) -> None:
        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin="https://bar.test",
            serve_path="/custom/path",
        )
        expected = "https://bar.test/custom/path"
        assert actual == expected


class Test_RequestSignature(unittest.TestCase):
    def test_success(self) -> None:
        body = json.dumps({"msg": "hi"}).encode("utf-8")
        unix_ms = round(time.time() * 1000)
        sig = _sign(body, _signing_key, unix_ms)
        assert not isinstance(sig, Exception)
        headers = {
            server_lib.HeaderKey.SIGNATURE.value: f"s={sig}&t={unix_ms}",
        }

        assert not isinstance(
            net.validate_sig(
                body=body,
                headers=headers,
                mode=server_lib.ServerKind.CLOUD,
                signing_key=_signing_key,
                signing_key_fallback=None,
            ),
            Exception,
        )

    def test_escape_sequences(self) -> None:
        unix_ms = round(time.time() * 1000)
        sig = _sign(b'{"msg":"a & b"}', _signing_key, unix_ms)
        assert not isinstance(sig, Exception)
        headers = {
            server_lib.HeaderKey.SIGNATURE.value: f"s={sig}&t={unix_ms}",
        }

        assert not isinstance(
            net.validate_sig(
                body=b'{"msg":"a \\u0026 b"}',
                headers=headers,
                mode=server_lib.ServerKind.CLOUD,
                signing_key=_signing_key,
                signing_key_fallback=None,
            ),
            Exception,
        )

    def test_body_tamper(self) -> None:
        """
        Validation fails if the body is changed after signature creation
        """

        body = json.dumps({"msg": "bar"}).encode("utf-8")
        unix_ms = round(time.time() * 1000)
        sig = _sign(body, _signing_key, unix_ms)
        assert not isinstance(sig, Exception)
        headers = {
            server_lib.HeaderKey.SIGNATURE.value: f"s={sig}&t={unix_ms}",
        }

        body = json.dumps({"msg": "you've been hacked"}).encode("utf-8")

        validation = net.validate_sig(
            body=body,
            headers=headers,
            mode=server_lib.ServerKind.CLOUD,
            signing_key=_signing_key,
            signing_key_fallback=None,
        )
        assert isinstance(validation, errors.SigVerificationFailedError)

    def test_rotation(self) -> None:
        """
        Validation succeeds if the primary signing key fails but the fallback
        signing key succeeds
        """

        body = json.dumps({"msg": "hi"}).encode("utf-8")
        unix_ms = round(time.time() * 1000)
        sig = _sign(body, _signing_key_fallback, unix_ms)
        assert not isinstance(sig, Exception)
        headers = {
            server_lib.HeaderKey.SIGNATURE.value: f"s={sig}&t={unix_ms}",
        }

        assert not isinstance(
            net.validate_sig(
                body=body,
                headers=headers,
                mode=server_lib.ServerKind.CLOUD,
                signing_key=_signing_key,
                signing_key_fallback=_signing_key_fallback,
            ),
            Exception,
        )

    def test_fails_for_both_signing_keys(self) -> None:
        """
        Validation fails after trying both the signing keys
        """

        body = json.dumps({"msg": "hi"}).encode("utf-8")
        unix_ms = round(time.time() * 1000)
        sig = _sign(body, "something-else", unix_ms)
        assert not isinstance(sig, Exception)
        headers = {
            server_lib.HeaderKey.SIGNATURE.value: f"s={sig}&t={unix_ms}",
        }

        assert isinstance(
            net.validate_sig(
                body=body,
                headers=headers,
                mode=server_lib.ServerKind.CLOUD,
                signing_key=_signing_key,
                signing_key_fallback=_signing_key_fallback,
            ),
            Exception,
        )


class Test_fetch_with_auth_fallback(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._req = httpx.Request("GET", "http://localhost")

    def _create_async_transport(
        self,
        handler: typing.Callable[[httpx.Request], httpx.Response],
    ) -> httpx.AsyncBaseTransport:
        class Transport(httpx.AsyncBaseTransport):
            async def handle_async_request(
                self,
                request: httpx.Request,
            ) -> httpx.Response:
                return handler(request)

        return Transport()

    def _create_transport(
        self,
        handler: typing.Callable[[httpx.Request], httpx.Response],
    ) -> httpx.BaseTransport:
        class Transport(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                return handler(request)

        return Transport()

    async def test_signing_key_works(self) -> None:
        """
        The signing key is valid, so the fallback isn't used
        """

        req_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal req_count
            req_count += 1

            actual_token = request.headers.get("authorization")
            if actual_token is None:
                return httpx.Response(401, content=b"", request=request)
            expected_token = (
                f"Bearer {transforms.hash_signing_key(_signing_key)}"
            )

            if actual_token != expected_token:
                return httpx.Response(401, content=b"", request=request)

            return httpx.Response(200, content=b"", request=request)

        res = await net.fetch_with_auth_fallback(
            net.ThreadAwareAsyncHTTPClient(
                transport=self._create_async_transport(handler)
            ).initialize(),
            httpx.Client(transport=self._create_transport(handler)),
            self._req,
            signing_key=_signing_key,
            signing_key_fallback=_signing_key_fallback,
        )
        assert not isinstance(res, Exception)
        assert res.status_code == 200
        assert req_count == 1
        req_count = 0

        res = net.fetch_with_auth_fallback_sync(
            httpx.Client(transport=self._create_transport(handler)),
            self._req,
            signing_key=_signing_key,
            signing_key_fallback=_signing_key_fallback,
        )
        assert not isinstance(res, Exception)
        assert res.status_code == 200
        assert req_count == 1

    async def test_signing_key_fallback_works(self) -> None:
        """
        The signing key is invalid, so the fallback is used
        """

        req_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal req_count
            req_count += 1

            actual_token = request.headers.get("authorization")
            if actual_token is None:
                return httpx.Response(401, content=b"", request=request)
            expected_token = (
                f"Bearer {transforms.hash_signing_key(_signing_key_fallback)}"
            )

            if actual_token != expected_token:
                return httpx.Response(401, content=b"", request=request)

            return httpx.Response(200, content=b"", request=request)

        res = await net.fetch_with_auth_fallback(
            net.ThreadAwareAsyncHTTPClient(
                transport=self._create_async_transport(handler)
            ).initialize(),
            httpx.Client(transport=self._create_transport(handler)),
            self._req,
            signing_key=_signing_key,
            signing_key_fallback=_signing_key_fallback,
        )
        assert not isinstance(res, Exception)
        assert res.status_code == 200
        assert req_count == 2
        req_count = 0

        res = net.fetch_with_auth_fallback_sync(
            httpx.Client(transport=self._create_transport(handler)),
            self._req,
            signing_key=_signing_key,
            signing_key_fallback=_signing_key_fallback,
        )
        assert not isinstance(res, Exception)
        assert res.status_code == 200
        assert req_count == 2

    async def test_signing_key_fallback_invalid(self) -> None:
        """
        Both signing keys are invalid
        """

        req_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal req_count
            req_count += 1

            actual_token = request.headers.get("authorization")
            if actual_token is None:
                return httpx.Response(401, content=b"", request=request)
            expected_token = (
                f"Bearer {transforms.hash_signing_key(_signing_key_fallback)}"
            )

            if actual_token != expected_token:
                return httpx.Response(401, content=b"", request=request)

            return httpx.Response(200, content=b"", request=request)

        res = await net.fetch_with_auth_fallback(
            net.ThreadAwareAsyncHTTPClient(
                transport=self._create_async_transport(handler)
            ).initialize(),
            httpx.Client(transport=self._create_transport(handler)),
            self._req,
            signing_key="signkey-prod-aaaaaa",
            signing_key_fallback="signkey-prod-bbbbbb",
        )
        assert not isinstance(res, Exception)
        assert res.status_code == 401
        assert req_count == 2
        req_count = 0

        res = net.fetch_with_auth_fallback_sync(
            httpx.Client(transport=self._create_transport(handler)),
            self._req,
            signing_key="signkey-prod-aaaaaa",
            signing_key_fallback="signkey-prod-bbbbbb",
        )
        assert not isinstance(res, Exception)
        assert res.status_code == 401
        assert req_count == 2

    async def test_no_signing_key(self) -> None:
        """
        Still send a request when we don't have a signing key.  This is
        necessary to work with the Dev Server
        """

        req_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal req_count
            req_count += 1

            actual_token = request.headers.get("authorization")
            if actual_token is not None:
                return httpx.Response(500, content=b"", request=request)

            return httpx.Response(200, content=b"", request=request)

        res = await net.fetch_with_auth_fallback(
            net.ThreadAwareAsyncHTTPClient(
                transport=self._create_async_transport(handler)
            ).initialize(),
            httpx.Client(transport=self._create_transport(handler)),
            self._req,
            signing_key=None,
            signing_key_fallback=None,
        )
        assert not isinstance(res, Exception)
        assert res.status_code == 200
        assert req_count == 1
        req_count = 0

        res = net.fetch_with_auth_fallback_sync(
            httpx.Client(transport=self._create_transport(handler)),
            self._req,
            signing_key=None,
            signing_key_fallback=None,
        )
        assert not isinstance(res, Exception)
        assert res.status_code == 200
        assert req_count == 1


class Test_parse_url(unittest.TestCase):
    def test_no_scheme(self) -> None:
        assert (
            net.parse_url("foo.test", mode=server_lib.ServerKind.CLOUD)
            == "https://foo.test"
        )
        assert (
            net.parse_url("foo.test", mode=server_lib.ServerKind.DEV_SERVER)
            == "http://foo.test"
        )

    def test_no_domain(self) -> None:
        assert (
            net.parse_url("http://foo:8080", mode=server_lib.ServerKind.CLOUD)
            == "http://foo:8080"
        )
        assert isinstance(
            net.parse_url("foo", mode=server_lib.ServerKind.CLOUD), Exception
        )
        assert isinstance(
            net.parse_url("http://foo", mode=server_lib.ServerKind.CLOUD),
            Exception,
        )

    def test_path(self) -> None:
        assert (
            net.parse_url(
                "http://foo:8080/bar", mode=server_lib.ServerKind.CLOUD
            )
            == "http://foo:8080/bar"
        )

    def test_boolean_strings(self) -> None:
        assert isinstance(
            net.parse_url("true", mode=server_lib.ServerKind.CLOUD), Exception
        )
        assert isinstance(
            net.parse_url("1", mode=server_lib.ServerKind.CLOUD), Exception
        )
        assert isinstance(
            net.parse_url("false", mode=server_lib.ServerKind.CLOUD), Exception
        )
        assert isinstance(
            net.parse_url("0", mode=server_lib.ServerKind.CLOUD), Exception
        )
        assert isinstance(
            net.parse_url("", mode=server_lib.ServerKind.CLOUD), Exception
        )


def _sign(body: bytes, signing_key: str, unix_ms: int) -> types.MaybeError[str]:
    canonicalized = transforms.canonicalize(body)
    if isinstance(canonicalized, Exception):
        return canonicalized

    signing_key = transforms.remove_signing_key_prefix(signing_key)

    mac = hmac.new(
        signing_key.encode("utf-8"),
        canonicalized,
        hashlib.sha256,
    )
    mac.update(str(unix_ms).encode("utf-8"))
    return mac.hexdigest()
