import asyncio
import json
import threading
import typing
import unittest

import fastapi
import httpx
import inngest
import inngest.fast_api
import test_core
import uvicorn
from test_core import base, http_proxy, net


class TestStreaming(unittest.IsolatedAsyncioTestCase):
    async def test_streaming_enabled(self) -> None:
        """
        Ensure that we get the correct response when streaming is enabled:
        - Status code is 201.
        - Keepalive bytes are sent.
        - The full streamed body is effectively an HTTP response (status code,
          headers, body).
        """

        sdk_port = net.get_available_port()

        res_status_codes = list[int]()
        res_headers = list[dict[str, str]]()
        res_chunks = list[bytes]()

        def on_request(
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> http_proxy.Response:
            with httpx.stream(
                method=method,
                url=f"http://0.0.0.0:{sdk_port}{path}",
                content=body,
                headers={k: v[0] for k, v in headers.items()},
            ) as resp:
                for chunk in resp.iter_bytes():
                    res_chunks.append(chunk)

            res_status_codes.append(resp.status_code)
            res_headers.append({k: v for k, v in resp.headers.items()})

            return http_proxy.Response(
                body=b"".join(res_chunks),
                headers=dict(resp.headers.items()),
                status_code=resp.status_code,
            )

        proxy = http_proxy.Proxy(on_request)
        proxy.start()
        self.addCleanup(proxy.stop)

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )

        state = test_core.BaseState()
        event_name = test_core.random_suffix("event")

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context, step: inngest.Step) -> str:
            state.run_id = ctx.run_id

            # Sleep long enough for first keepalive byte to send.
            await asyncio.sleep(4)

            return "Hi"

        def start_app() -> None:
            app = fastapi.FastAPI()
            inngest.fast_api.serve(
                app,
                client,
                [fn],
                serve_origin=proxy.origin,
                streaming=True,
            )
            uvicorn.run(app, host="0.0.0.0", port=sdk_port, log_level="warning")

        app_thread = threading.Thread(daemon=True, target=start_app)
        app_thread.start()
        self.addCleanup(app_thread.join, timeout=1)
        base.register(sdk_port)

        await client.send(inngest.Event(name=event_name))

        run = await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        assert json.loads(run.output) == "Hi"

        # This status code tells the Inngest server that we're streaming.
        assert res_status_codes == [201]

        # We got a keepalive byte.
        assert res_chunks[0] == b" "

        # The final chunk is the wrapped response.
        wrapped_resp = json.loads(res_chunks[len(res_chunks) - 1])
        assert isinstance(wrapped_resp, dict)

        # Body we would've gotten if we weren't streaming.
        assert wrapped_resp["body"] == '"Hi"'

        # Status code we would've gotten if we weren't streaming.
        assert wrapped_resp["status"] == 200

        # Headers we would've gotten if we weren't streaming.
        assert wrapped_resp["headers"].get("x-inngest-sdk") is not None

    async def test_streaming_disabled(self) -> None:
        """
        Ensure that we get the correct response when streaming is disabled:
        - Status code is 200.
        - No keepalive bytes are sent.
        - The body is the function output.
        """

        sdk_port = net.get_available_port()

        res_status_codes = list[int]()
        res_headers = list[dict[str, str]]()
        res_chunks = list[bytes]()

        def on_request(
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> http_proxy.Response:
            with httpx.stream(
                method=method,
                url=f"http://0.0.0.0:{sdk_port}{path}",
                content=body,
                headers={k: v[0] for k, v in headers.items()},
            ) as resp:
                for chunk in resp.iter_bytes():
                    res_chunks.append(chunk)

            res_status_codes.append(resp.status_code)
            res_headers.append({k: v for k, v in resp.headers.items()})

            return http_proxy.Response(
                body=b"".join(res_chunks),
                headers=dict(resp.headers.items()),
                status_code=resp.status_code,
            )

        proxy = http_proxy.Proxy(on_request)
        proxy.start()
        self.addCleanup(proxy.stop)

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )

        state = test_core.BaseState()
        event_name = test_core.random_suffix("event")

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context, step: inngest.Step) -> str:
            state.run_id = ctx.run_id

            # Sleep long enough for first keepalive byte to send.
            await asyncio.sleep(4)

            return "Hi"

        def start_app() -> None:
            app = fastapi.FastAPI()
            inngest.fast_api.serve(
                app,
                client,
                [fn],
                serve_origin=proxy.origin,
            )
            uvicorn.run(app, host="0.0.0.0", port=sdk_port, log_level="warning")

        app_thread = threading.Thread(daemon=True, target=start_app)
        app_thread.start()
        self.addCleanup(app_thread.join, timeout=1)
        base.register(sdk_port)

        await client.send(inngest.Event(name=event_name))

        run = await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        assert json.loads(run.output) == "Hi"

        # This status code tells the Inngest server that we're not streaming.
        assert res_status_codes == [200]

        # We didn't get a keepalive byte.
        assert res_chunks == [b'"Hi"']
