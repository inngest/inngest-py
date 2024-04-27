import datetime
import hashlib
import hmac
import os
import time
import typing
import unittest

import httpx

import inngest
from inngest._internal import const, transforms, types

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


def register(app_port: int) -> None:
    res = httpx.put(
        f"http://{net.HOST}:{app_port}/api/inngest",
        timeout=5,
    )
    assert res.status_code == 200


def set_up(case: _FrameworkTestCase) -> None:
    case.proxy = http_proxy.Proxy(case.on_proxy_request).start()


def tear_down(case: _FrameworkTestCase) -> None:
    case.proxy.stop()


class IntrospectionResponse(types.BaseModel):
    body: object
    status_code: int


class BaseTestIntrospection(unittest.TestCase):
    signing_key = "signkey-prod-123abc"

    def setUp(self) -> None:
        self.expected_insecure_body = {
            "function_count": 1,
            "has_event_key": True,
            "has_signing_key": True,
            "mode": "cloud",
        }

        self.expected_secure_body = {
            "function_count": 1,
            "has_event_key": True,
            "has_signing_key": True,
            "mode": "cloud",
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

    def set_signing_key_fallback_env_var(self) -> None:
        os.environ[
            const.EnvKey.SIGNING_KEY_FALLBACK.value
        ] = "signkey-prod-456def"
        self.addCleanup(
            lambda: os.environ.pop(const.EnvKey.SIGNING_KEY_FALLBACK.value)
        )
