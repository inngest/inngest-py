from __future__ import annotations

import asyncio
import threading
import typing
import unittest

import flask
import httpx
import inngest
import inngest.flask
import test_core
from test_core import base, http_proxy, net


class TestStreaming(unittest.IsolatedAsyncioTestCase):
    def start_proxy(
        self,
        client: inngest.Inngest,
        fns: list[inngest.Function[typing.Any]],
    ) -> list[Resp]:
        sdk_port = net.get_available_port()
        resps: list[Resp] = []

        def on_request(
            body: typing.Optional[bytes],
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
            app = flask.Flask(__name__)
            inngest.flask.serve(
                app,
                client,
                fns,
                serve_origin=proxy.origin,
            )
            app.run(threaded=True, port=sdk_port)

        app_thread = threading.Thread(daemon=True, target=start_app)
        app_thread.start()
        self.addCleanup(app_thread.join, timeout=1)
        base.register(sdk_port)

        return resps

    async def test_main(self) -> None:
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

            # Sleep long enough for first keepalive byte to send.
            await asyncio.sleep(0.4)

        resps = self.start_proxy(client, [fn])

        await client.send(inngest.Event(name=event_name))
        await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )

        timings = parse_timings(resps[0].headers["server-timing"])
        assert_approx_timing(timings["comm_handler"], 700)
        assert_approx_timing(timings["function"], 400)
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
