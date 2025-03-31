import asyncio
import dataclasses
import typing

import inngest
import test_core
import test_core.http_proxy
import test_core.net
import test_core.ws_proxy
from inngest.experimental.connect import connect

from .base import BaseTest


class TestAPIRequestHeaders(BaseTest):
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
