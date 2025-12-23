import asyncio
import datetime
import inspect
import os
import time
import typing
import unittest
import urllib.parse

import httpx
import inngest
from inngest._internal import const, server_lib

from . import http_proxy, net


class BaseState:
    run_id: str | None = None

    async def wait_for_run_id(
        self,
        *,
        timeout: datetime.timedelta = datetime.timedelta(seconds=5),
    ) -> str:
        def assertion() -> None:
            assert self.run_id is not None

        await wait_for(assertion, timeout=timeout)
        assert self.run_id is not None
        return self.run_id


async def wait_for(
    assertion: typing.Callable[[], None]
    | typing.Callable[[], typing.Awaitable[None]],
    *,
    timeout: datetime.timedelta = datetime.timedelta(seconds=5),
) -> None:
    start = datetime.datetime.now()
    while True:
        try:
            if inspect.iscoroutinefunction(assertion):
                await assertion()
            else:
                assertion()
            return
        except Exception as err:
            timed_out = datetime.datetime.now() > start + timeout
            if timed_out:
                raise err

        await asyncio.sleep(0.2)


async def wait_for_len(
    get_value: typing.Callable[[], typing.Sequence[object]],
    length: int,
    *,
    timeout: datetime.timedelta = datetime.timedelta(seconds=5),
) -> None:
    def assertion() -> None:
        assert len(get_value()) == length

    await wait_for(assertion, timeout=timeout)


async def wait_for_truthy(
    get_value: typing.Callable[[], object],
    *,
    timeout: datetime.timedelta = datetime.timedelta(seconds=5),
) -> None:
    def assertion() -> None:
        assert bool(get_value())

    await wait_for(assertion, timeout=timeout)


class _FrameworkTestCase(typing.Protocol):
    dev_server_port: int
    proxy: http_proxy.Proxy

    def on_proxy_request(
        self,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> http_proxy.Response: ...


def create_test_name(file: str) -> str:
    return os.path.basename(file).replace(".py", "").removeprefix("test_")


def register(
    app_port: int,
    path: str | None = "/api/inngest",
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


class BaseTest(unittest.TestCase):
    signing_key = "signkey-prod-123abc"

    def create_functions(
        self,
        client: inngest.Inngest,
    ) -> list[inngest.Function[typing.Any]]:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> None:
            pass

        return [fn]

    def set_signing_key_fallback_env_var(self) -> str:
        signing_key = "signkey-prod-456def"
        os.environ[const.EnvKey.SIGNING_KEY_FALLBACK.value] = signing_key
        self.addCleanup(
            lambda: os.environ.pop(const.EnvKey.SIGNING_KEY_FALLBACK.value)
        )
        return signing_key


class BaseTestIntrospection(BaseTest):
    framework: server_lib.Framework

    def setUp(self) -> None:
        self.expected_unauthed_body = {
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
            "capabilities": {
                "connect": "v1",
                "in_band_sync": "v1",
                "trust_probe": "v1",
            },
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
