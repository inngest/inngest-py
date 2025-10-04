from __future__ import annotations

import asyncio
import json
import threading
import time
import typing
import unittest

import fastapi
import httpx
import inngest
import inngest.fast_api
import test_core
import uvicorn
from inngest._internal import types
from test_core import base, http_proxy, net


class TestStreaming(unittest.IsolatedAsyncioTestCase):
    def start_proxy(
        self,
        client: inngest.Inngest,
        fns: list[inngest.Function[typing.Any]],
        streaming: inngest.Streaming,
    ) -> list[Resp]:
        sdk_port = net.get_available_port()
        resps: list[Resp] = []

        def on_request(
            body: bytes | None,
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> http_proxy.Response:
            resp_data = Resp()
            with httpx.stream(
                method=method,
                url=f"http://0.0.0.0:{sdk_port}{path}",
                content=body,
                headers={k: v[0] for k, v in headers.items()},
            ) as resp:
                for chunk in resp.iter_bytes():
                    resp_data.chunks.append(chunk)

            resp_data.status_code = resp.status_code
            resp_data.headers = {k: v for k, v in resp.headers.items()}
            resps.append(resp_data)

            return http_proxy.Response(
                body=b"".join(resp_data.chunks),
                headers=dict(resp.headers.items()),
                status_code=resp.status_code,
            )

        proxy = http_proxy.Proxy(on_request)
        proxy.start()
        self.addCleanup(proxy.stop)

        def start_app() -> None:
            app = fastapi.FastAPI()
            inngest.fast_api.serve(
                app,
                client,
                fns,
                serve_origin=proxy.origin,
                streaming=streaming,
            )
            uvicorn.run(app, host="0.0.0.0", port=sdk_port, log_level="warning")  # pyright: ignore[reportUnknownMemberType]

        app_thread = threading.Thread(daemon=True, target=start_app)
        app_thread.start()
        self.addCleanup(app_thread.join, timeout=1)
        base.register(sdk_port)

        return resps

    async def test_streaming_enabled(self) -> None:
        """
        When streaming is enabled, the comm_handler timing is basically 0
        because we immediately respond
        """

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
            middleware=[Middleware],
        )

        state = test_core.BaseState()
        event_name = test_core.random_suffix("event")

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> None:
            state.run_id = ctx.run_id
            await asyncio.sleep(0.4)

        resps = self.start_proxy(client, [fn], inngest.Streaming.FORCE)

        await client.send(inngest.Event(name=event_name))
        await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )

        # The final chunk is the wrapped response.
        wrapped_resp = json.loads(resps[0].chunks[len(resps[0].chunks) - 1])
        assert types.is_dict(wrapped_resp)

        headers = wrapped_resp["headers"]
        assert types.is_dict(headers)
        timings = parse_timings(headers["server-timing"])
        assert_approx_timing(timings["async_block"], 0)
        assert_approx_timing(timings["comm_handler"], 0)
        assert_approx_timing(timings["function"], 400)
        assert_approx_timing(timings["mw.transform_input"], 100)
        assert_approx_timing(timings["mw.transform_output"], 200)

    async def test_streaming_disabled(self) -> None:
        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
            middleware=[Middleware],
        )

        state = test_core.BaseState()
        event_name = test_core.random_suffix("event")

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> None:
            state.run_id = ctx.run_id
            await asyncio.sleep(0.4)

        resps = self.start_proxy(client, [fn], inngest.Streaming.DISABLE)

        await client.send(inngest.Event(name=event_name))
        await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )

        timings = parse_timings(resps[0].headers["server-timing"])
        assert_approx_timing(timings["async_block"], 0)
        assert_approx_timing(timings["comm_handler"], 700)
        assert_approx_timing(timings["function"], 400)
        assert_approx_timing(timings["mw.transform_input"], 100)
        assert_approx_timing(timings["mw.transform_output"], 200)

    async def test_async_block(self) -> None:
        """
        Blocking the event loop (e.g. with `time.sleep`) is reported in the
        async_block timing
        """

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
            middleware=[Middleware],
        )

        state = test_core.BaseState()
        event_name = test_core.random_suffix("event")

        blocking_sleep_dur = 300
        async_sleep_dur = 400

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> None:
            state.run_id = ctx.run_id

            # Block the thread, leading to async_block duration
            time.sleep(blocking_sleep_dur / 1000.0)  # noqa: ASYNC251

            await asyncio.sleep(async_sleep_dur / 1000.0)

        resps = self.start_proxy(client, [fn], inngest.Streaming.DISABLE)

        await client.send(inngest.Event(name=event_name))
        await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )

        timings = parse_timings(resps[0].headers["server-timing"])
        assert_approx_timing(timings["async_block"], blocking_sleep_dur)
        assert_approx_timing(timings["comm_handler"], 1000)
        assert_approx_timing(
            timings["function"],
            blocking_sleep_dur + async_sleep_dur,
        )
        assert_approx_timing(timings["mw.transform_input"], 100)
        assert_approx_timing(timings["mw.transform_output"], 200)


def assert_approx_timing(actual: int, approx_expected: int) -> None:
    assert actual >= approx_expected

    # Allow some arbitrary margin of error
    assert actual < approx_expected + 100


def parse_timings(timings_value: object) -> dict[str, int]:
    assert isinstance(timings_value, str)
    timings: dict[str, int] = {}
    for timing in timings_value.split(","):
        name, dur = timing.split(";dur=")
        timings[name.strip()] = int(dur)
    return timings


class Middleware(inngest.Middleware):
    async def transform_input(
        self,
        ctx: inngest.Context | inngest.ContextSync,
        function: inngest.Function[typing.Any],
        steps: inngest.StepMemos,
    ) -> None:
        await asyncio.sleep(0.1)

    async def transform_output(
        self,
        result: inngest.TransformOutputResult,
    ) -> None:
        await asyncio.sleep(0.2)


class Resp:
    def __init__(self) -> None:
        self.chunks = list[bytes]()
        self.headers = dict[str, str]()
        self.status_code = 0
