import datetime
import hashlib
import hmac
import os
import time
import typing
import unittest
import urllib.parse

import httpx

import inngest
from inngest._internal import const, server_lib, transforms, types

from . import http_proxy, net


class BaseState:
    run_id: typing.Optional[str] = None

    def wait_for_run_id(
        self,
        *,
        timeout: datetime.timedelta = datetime.timedelta(seconds=5),
    ) -> str:
        def assertion() -> None:
            assert self.run_id is not None

        wait_for(assertion, timeout=timeout)
        assert self.run_id is not None
        return self.run_id


def wait_for(
    assertion: typing.Callable[[], None],
    *,
    timeout: datetime.timedelta = datetime.timedelta(seconds=5),
) -> None:
    start = datetime.datetime.now()
    while True:
        try:
            assertion()
            return
        except Exception as err:
            timed_out = datetime.datetime.now() > start + timeout
            if timed_out:
                raise err

        time.sleep(0.2)


class _FrameworkTestCase(typing.Protocol):
    dev_server_port: int
    proxy: http_proxy.Proxy

    def on_proxy_request(
        self,
        *,
        body: typing.Optional[bytes],
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> http_proxy.Response:
        ...


def create_app_id(framework: str) -> str:
    suffix = ""
    worker_id = os.getenv("PYTEST_XDIST_WORKER")
    if worker_id:
        suffix += f"-{worker_id}"

    return framework + suffix


def create_test_name(file: str) -> str:
    return os.path.basename(file).replace(".py", "").removeprefix("test_")


def register(
    app_port: int,
    path: typing.Optional[str] = "/api/inngest",
) -> None:
    start = time.time()
    while time.time() < start + 5:
        try:
            res = httpx.put(
                urllib.parse.urljoin(f"http://{net.HOST}:{app_port}", path),
                timeout=5,
            )
            assert res.status_code == 200
            return
        except Exception:
            time.sleep(0.1)


def set_up(case: _FrameworkTestCase) -> None:
    case.proxy = http_proxy.Proxy(case.on_proxy_request).start()


def tear_down(case: _FrameworkTestCase) -> None:
    case.proxy.stop()


class IntrospectionResponse(types.BaseModel):
    body: object
    status_code: int


class BaseTestIntrospection(unittest.TestCase):
    framework: server_lib.Framework
    signing_key = "signkey-prod-123abc"

    def setUp(self) -> None:
        self.expected_unauthed_body = {
            "authentication_succeeded": None,
            "function_count": 1,
            "has_event_key": True,
            "has_signing_key": True,
            "has_signing_key_fallback": False,
            "mode": "cloud",
            "schema_version": "2024-05-24",
        }

        self.expected_authed_body = {
            **self.expected_unauthed_body,
            "api_origin": "https://api.inngest.com/",
            "app_id": "my-app",
            "authentication_succeeded": True,
            "env": None,
            "event_api_origin": "https://inn.gs/",
            "event_key_hash": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            "framework": self.framework.value,
            "sdk_language": const.LANGUAGE,
            "sdk_version": const.VERSION,
            "serve_origin": None,
            "serve_path": None,
            "signing_key_fallback_hash": "a820760dee6119fcf76498ab8d94be2f8cf04e786add2a4569e427462a84dd47",
            "signing_key_hash": "94bab7f22b92278ccab46e15da43a9fb8b079c05fa099d4134c6c39bbcee49f6",
        }

    def create_functions(
        self, client: inngest.Inngest
    ) -> list[inngest.Function]:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> None:
            pass

        return [fn]

    def create_signature(self) -> str:
        mac = hmac.new(
            transforms.remove_signing_key_prefix(self.signing_key).encode(
                "utf-8"
            ),
            b"",
            hashlib.sha256,
        )
        unix_ms = round(time.time() * 1000)
        mac.update(str(unix_ms).encode("utf-8"))
        sig = mac.hexdigest()
        return f"s={sig}&t={unix_ms}"

    def validate_signature(self, sig: str, body: bytes) -> None:
        parsed = urllib.parse.parse_qs(sig)
        timestamp = int(parsed["t"][0])
        signature = parsed["s"][0]

        mac = hmac.new(
            transforms.remove_signing_key_prefix(self.signing_key).encode(
                "utf-8"
            ),
            body,
            hashlib.sha256,
        )

        if timestamp:
            mac.update(str(timestamp).encode("utf-8"))

        if not hmac.compare_digest(signature, mac.hexdigest()):
            raise Exception("invalid signature")

    def set_signing_key_fallback_env_var(self) -> None:
        os.environ[
            const.EnvKey.SIGNING_KEY_FALLBACK.value
        ] = "signkey-prod-456def"
        self.addCleanup(
            lambda: os.environ.pop(const.EnvKey.SIGNING_KEY_FALLBACK.value)
        )
