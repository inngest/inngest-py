import hashlib
import hmac
import json
import os
import time
import unittest

from . import const, errors, net


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
        assert actual == expected, actual

    def test_serve_origin(self) -> None:
        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin="https://bar.test",
            serve_path=None,
        )
        expected = "https://bar.test/api/inngest"
        assert actual == expected, actual

    def test_serve_origin_env_var(self) -> None:
        os.environ[const.EnvKey.SERVE_ORIGIN.value] = "https://bar-env.test"

        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin="https://bar.test",
            serve_path=None,
        )
        expected = "https://bar-env.test/api/inngest"
        assert actual == expected, actual

    def test_serve_origin_missing_scheme(self) -> None:
        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin="bar.test",
            serve_path=None,
        )
        expected = "https://bar.test/api/inngest"
        assert actual == expected, actual

    def test_serve_origin_port(self) -> None:
        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin="https://bar.test:8080",
            serve_path=None,
        )
        expected = "https://bar.test:8080/api/inngest"
        assert actual == expected, actual

    def test_serve_path(self) -> None:
        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin=None,
            serve_path="/custom/path",
        )
        expected = "https://foo.test/custom/path"
        assert actual == expected, actual

    def test_serve_path_env_var(self) -> None:
        os.environ[const.EnvKey.SERVE_PATH.value] = "/env/path"

        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin=None,
            serve_path="/custom/path",
        )
        expected = "https://foo.test/env/path"
        assert actual == expected, actual

    def test_serve_origin_and_path(self) -> None:
        actual = net.create_serve_url(
            request_url="https://foo.test/api/inngest",
            serve_origin="https://bar.test",
            serve_path="/custom/path",
        )
        expected = "https://bar.test/custom/path"
        assert actual == expected, actual


def test_success() -> None:
    body = json.dumps({"msg": "hi"}).encode("utf-8")
    signing_key = "super-secret"
    unix_ms = round(time.time() * 1000)
    sig = _sign(body, signing_key, unix_ms)
    headers = {
        const.HeaderKey.SIGNATURE.value: f"s={sig}&t={unix_ms}",
    }

    req_sig = net.RequestSignature(body, headers, is_production=True)
    assert not isinstance(req_sig.validate(signing_key), Exception)


def test_body_tamper() -> None:
    body = json.dumps({"msg": "bar"}).encode("utf-8")
    signing_key = "super-secret"
    unix_ms = round(time.time() * 1000)
    sig = _sign(body, signing_key, unix_ms)
    headers = {
        const.HeaderKey.SIGNATURE.value: f"s={sig}&t={unix_ms}",
    }

    body = json.dumps({"msg": "you've been hacked"}).encode("utf-8")
    req_sig = net.RequestSignature(body, headers, is_production=True)

    validation = req_sig.validate(signing_key)
    assert isinstance(validation, errors.InvalidRequestSignatureError)


def _sign(body: bytes, signing_key: str, unix_ms: int) -> str:
    mac = hmac.new(
        signing_key.encode("utf-8"),
        body,
        hashlib.sha256,
    )
    mac.update(str(unix_ms).encode("utf-8"))
    return mac.hexdigest()
    return mac.hexdigest()
    return mac.hexdigest()
