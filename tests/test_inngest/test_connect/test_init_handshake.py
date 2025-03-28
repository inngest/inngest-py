import asyncio
import dataclasses
import json
import typing
import unittest

import httpx
import inngest
import pytest
import test_core
import test_core.http_proxy
import test_core.net
import test_core.ws_proxy
from inngest.experimental.connect import connect, connect_pb2


class TestAPIRequestHeaders(unittest.IsolatedAsyncioTestCase):
    @pytest.mark.timeout(5)
    async def test_cloud(self) -> None:
        """
        Connect sends the authorization header in the initial API request.
        """

        @dataclasses.dataclass
        class State:
            outgoing_headers: dict[str, list[str]]

        state = State(outgoing_headers={})

        def mock_api_handler(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> test_core.http_proxy.Response:
            state.outgoing_headers = headers
            return test_core.http_proxy.Response(
                body=b"",
                headers={},
                status_code=200,
            )

        mock_api = test_core.http_proxy.Proxy(mock_api_handler).start()
        self.addCleanup(mock_api.stop)
        client = inngest.Inngest(
            app_id="app",
            api_base_url=f"http://{mock_api.host}:{mock_api.port}",
            signing_key="deadbeef",
        )

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn(ctx: inngest.Context, step: inngest.Step) -> None:
            pass

        conn = connect(
            [(client, [fn])],
        )
        self.addCleanup(conn.close, wait=True)
        task = asyncio.create_task(conn.start())
        self.addCleanup(task.cancel)

        def assert_headers() -> None:
            assert state.outgoing_headers["authorization"] == [
                "Bearer 5f78c33274e43fa9de5659265c1d917e25c03722dcb0b8d27db8d5feaa813953"
            ]

        await test_core.wait_for(assert_headers)

    @pytest.mark.timeout(5)
    async def test_dev(self) -> None:
        """
        Connect does not send the authorization header in the initial API
        request.
        """

        @dataclasses.dataclass
        class State:
            outgoing_headers: dict[str, list[str]]

        state = State(outgoing_headers={})

        def mock_api_handler(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> test_core.http_proxy.Response:
            state.outgoing_headers = headers
            return test_core.http_proxy.Response(
                body=b"",
                headers={},
                status_code=200,
            )

        mock_api = test_core.http_proxy.Proxy(mock_api_handler).start()
        self.addCleanup(mock_api.stop)
        client = inngest.Inngest(
            app_id="app",
            api_base_url=f"http://{mock_api.host}:{mock_api.port}",
            is_production=False,
            signing_key="deadbeef",
        )

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn(ctx: inngest.Context, step: inngest.Step) -> None:
            pass

        conn = connect(
            [(client, [fn])],
        )
        self.addCleanup(conn.close, wait=True)
        task = asyncio.create_task(conn.start())
        self.addCleanup(task.cancel)

        await test_core.wait_for_truthy(lambda: state.outgoing_headers)
        assert "authorization" not in state.outgoing_headers

    @pytest.mark.timeout(10)
    async def test_example_proxy(self) -> None:
        """
        Use this as an example as we write more tests.
        """

        ws_proxy = test_core.ws_proxy.WebSocketProxy(
            "ws://0.0.0.0:8289/v0/connect"
        )
        self.addCleanup(ws_proxy.stop)
        await ws_proxy.start()

        def http_proxy_handler(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> test_core.http_proxy.Response:
            resp = httpx.request(
                content=body,
                headers={k: v[0] for k, v in headers.items()},
                method=method,
                url=f"http://0.0.0.0:8288{path}",
            )

            start_resp = connect_pb2.StartResponse()
            start_resp.ParseFromString(resp.content)
            start_resp.gateway_endpoint = ws_proxy.url

            resp_body = start_resp.SerializeToString()
            resp_headers = {k: v[0] for k, v in resp.headers.items()}
            resp_headers["content-length"] = str(len(resp_body))

            return test_core.http_proxy.Response(
                body=resp_body,
                headers=resp_headers,
                status_code=resp.status_code,
            )

        http_proxy = test_core.http_proxy.Proxy(http_proxy_handler).start()
        self.addCleanup(http_proxy.stop)

        client = inngest.Inngest(
            api_base_url=f"http://0.0.0.0:{http_proxy.port}",
            app_id="app",
            is_production=False,
        )

        @dataclasses.dataclass
        class State(test_core.BaseState):
            step_counter = 0

        state = State()

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn(ctx: inngest.Context, step: inngest.Step) -> str:
            state.run_id = ctx.run_id

            def step_a() -> str:
                state.step_counter += 1
                return "Alice"

            name = await step.run("a", step_a)
            return f"Hello {name}"

        conn = connect([(client, [fn])])
        task = asyncio.create_task(conn.start())
        self.addCleanup(conn.close, wait=True)
        self.addCleanup(task.cancel)

        # Trigger the function and wait for it to complete.
        await client.send(inngest.Event(name="event"))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        assert json.loads(run.output) == "Hello Alice"
        self.assertEqual(state.step_counter, 1)
